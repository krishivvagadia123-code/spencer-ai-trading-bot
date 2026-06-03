"""
Mistake Review Engine — read-only post-mortem on Spencer's trade journals.

It answers ONE question honestly: *why are trades losing?* It then writes a small
DOWN-ONLY trust table the router can consult to avoid repeating the same bad trades.

Hard guarantees (by design):
  - READ-ONLY. It never edits live config, never places orders, never re-optimizes.
  - DOWN-ONLY trust in [TRUST_FLOOR, 1.0]. Trust can only shrink size / skip trades; it
    can never increase risk. A bucket with no edge gets 1.0 (neutral), never > 1.0.
  - NO fabricated improvement. Every number is computed from real closed trades.
  - Min-sample gating: a bucket below MIN_SAMPLE stays neutral (we don't punish noise).

Eight loss causes are detected per losing trade:
  1. bad_regime      6. stop_too_tight
  2. weak_entry      7. bad_symbol
  3. overtrading     8. bad_setup
  4. high_charges
  5. bad_risk_reward

Outputs:
  - MISTAKE_REVIEW.md  — the human report (top reasons, worst symbols/regimes/strategies,
                         repeated mistakes, what should have been rejected, what to test next).
  - mistake_trust.json — {symbol, regime, strategy, setup} trust tables for the router.
"""

from __future__ import annotations

import glob
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
TRUST_PATH = BASE_DIR / "mistake_trust.json"
REPORT_PATH = BASE_DIR / "MISTAKE_REVIEW.md"


@dataclass(frozen=True)
class MistakeConfig:
    min_sample:        int   = 20     # regime/setup/strategy: below this stays neutral
    symbol_min_sample: int   = 8      # symbols trade less often -> lower (still coarse, down-only)
    trust_floor:       float = 0.25   # never shrink below 25%
    weak_entry_score:  float = 0.68   # entry score below this = marginal/weak signal
    setup_strong:      float = 0.73   # >= strong band
    setup_moderate:    float = 0.68   # >= moderate band, else marginal
    min_rr:            float = 1.50   # below this = bad risk-reward
    high_charge_ratio: float = 0.20   # charges >= 20% of target reward = high charges
    charge_vs_loss:    float = 0.30   # charges >= 30% of the realized loss = high charges
    tight_bars:        int   = 2      # stopped within <=2 bars ...
    tight_stop_pct:    float = 0.01   # ... and stop < 1% away = stop too tight
    overtrade_symbol_n: int  = 15     # > this many trades in one symbol = overtrading-prone
    reentry_days:      int   = 5      # re-entering a symbol within N days of a loss


# Where each strategy's trades live (latest run of each file). Keeps strategy trust
# from double-counting accumulated runs.
STRATEGY_SOURCES = [
    ("backtest_journal.db",   "baseline"),
    ("backtest_v1_volume.db", "v1_volume"),
    ("backtest_v2_regime.db", "v2_regime"),
    ("backtest_v3_targets.db","v3_targets"),
    ("backtest_v_all.db",     "v_all"),
    ("backtest_filtered.db",  "filtered"),
]


# ── Loading ──────────────────────────────────────────────────────────────────
def _latest_run_id(conn) -> Optional[int]:
    row = conn.execute("SELECT MAX(run_id) FROM backtest_trades").fetchone()
    return row[0] if row else None


def load_trades(db_path: str | Path) -> List[dict]:
    """Load closed trades from one backtest journal (its latest run only)."""
    p = Path(db_path)
    if not p.exists():
        return []
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        rid = _latest_run_id(conn)
        if rid is None:
            return []
        rows = conn.execute(
            "SELECT symbol, regime, entry_date, exit_date, entry, stop, target, exit, "
            "qty, entry_score, exit_reason, bars_held, gross_pnl, charges, pnl "
            "FROM backtest_trades WHERE run_id=? ORDER BY entry_date ASC", (rid,)
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_paper_context(kite_db: str | Path = "kite_bot.db") -> dict:
    """Summarize the live paper journal for context (not used for mistake stats —
    its only closed trades are forced exits, which are not strategy mistakes)."""
    p = Path(kite_db)
    if not p.exists():
        return {"closed": 0, "note": "no paper journal"}
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT pnl, exit_reason FROM trades WHERE action='SELL' AND pnl IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    reasons = Counter(r["exit_reason"] for r in rows)
    return {
        "closed": len(rows),
        "net_pnl": round(sum(r["pnl"] for r in rows), 2),
        "exit_reasons": dict(reasons),
        "note": "all closed paper trades are forced exits (FLATTEN/migration) — "
                "excluded from mistake stats as they are not strategy decisions.",
    }


# ── Derived per-trade fields ─────────────────────────────────────────────────
def _rr(t: dict) -> Optional[float]:
    risk = (t["entry"] or 0) - (t["stop"] or 0)
    if risk <= 0:
        return None
    return ((t["target"] or 0) - (t["entry"] or 0)) / risk


def _stop_pct(t: dict) -> Optional[float]:
    if not t["entry"]:
        return None
    return ((t["entry"] - (t["stop"] or 0)) / t["entry"]) if t["entry"] else None


def _target_reward(t: dict) -> float:
    return ((t["target"] or 0) - (t["entry"] or 0)) * (t["qty"] or 0)


def setup_of(entry_score: Optional[float], cfg: MistakeConfig) -> str:
    if entry_score is None:
        return "unknown"
    if entry_score >= cfg.setup_strong:
        return "strong"
    if entry_score >= cfg.setup_moderate:
        return "moderate"
    return "marginal"


# ── Trust math (down-only, mirrors regime_learner) ───────────────────────────
def _trust(avg: float, overall: float, cfg: MistakeConfig) -> float:
    if avg >= 0:
        return 1.0
    anchor = abs(overall) if overall < 0 else max(1.0, abs(overall))
    severity = min(1.0, abs(avg) / (anchor + 1e-9))
    return round(max(cfg.trust_floor, 1.0 - severity * (1.0 - cfg.trust_floor)), 4)


def _bucket_table(trades: List[dict], keyfn, overall_avg: float, cfg: MistakeConfig,
                  min_sample: Optional[int] = None) -> dict:
    min_sample = cfg.min_sample if min_sample is None else min_sample
    groups: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        groups[keyfn(t)].append(t["pnl"])
    out = {}
    for k, pnls in groups.items():
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        avg = sum(pnls) / n
        sufficient = n >= min_sample
        trust = _trust(avg, overall_avg, cfg) if sufficient else 1.0
        out[k] = {
            "trades": n, "win_rate": round(wins / n, 4), "net_pnl": round(sum(pnls), 2),
            "avg_pnl": round(avg, 2), "trust": trust, "sufficient": sufficient,
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["avg_pnl"]))


# ── Mistake classification ───────────────────────────────────────────────────
def classify(t: dict, ctx: dict, cfg: MistakeConfig) -> List[str]:
    """Return the loss reasons that apply to ONE losing trade."""
    reasons: List[str] = []
    if t["regime"] in ctx["bad_regimes"]:
        reasons.append("bad_regime")
    if t["entry_score"] is not None and t["entry_score"] < cfg.weak_entry_score:
        reasons.append("weak_entry")
    if ctx["symbol_counts"].get(t["symbol"], 0) > cfg.overtrade_symbol_n \
            or t["symbol"] in ctx["reentry_after_loss"]:
        reasons.append("overtrading")
    tr = _target_reward(t)
    if (tr > 0 and t["charges"] / tr >= cfg.high_charge_ratio) \
            or (t["pnl"] < 0 and t["charges"] >= cfg.charge_vs_loss * abs(t["pnl"])):
        reasons.append("high_charges")
    rr = _rr(t)
    if rr is not None and rr < cfg.min_rr:
        reasons.append("bad_risk_reward")
    sp = _stop_pct(t)
    if t["exit_reason"] == "stop" and (t["bars_held"] or 99) <= cfg.tight_bars \
            and sp is not None and sp <= cfg.tight_stop_pct:
        reasons.append("stop_too_tight")
    if t["symbol"] in ctx["bad_symbols"]:
        reasons.append("bad_symbol")
    if setup_of(t["entry_score"], cfg) in ctx["bad_setups"]:
        reasons.append("bad_setup")
    return reasons


# Reasons knowable BEFORE entry (a router could act on these).
PRE_TRADE_REASONS = {"bad_regime", "weak_entry", "high_charges",
                     "bad_risk_reward", "bad_symbol", "bad_setup"}


# ── Main analysis ────────────────────────────────────────────────────────────
def analyze(trades: List[dict], cfg: MistakeConfig = MistakeConfig()) -> dict:
    n = len(trades)
    if n == 0:
        return {"error": "no trades to analyze"}
    overall_avg = sum(t["pnl"] for t in trades) / n

    # Trust tables.
    regime_trust = _bucket_table(trades, lambda t: t["regime"], overall_avg, cfg)
    symbol_trust = _bucket_table(trades, lambda t: t["symbol"], overall_avg, cfg,
                                 min_sample=cfg.symbol_min_sample)
    setup_trust  = _bucket_table(trades, lambda t: setup_of(t["entry_score"], cfg), overall_avg, cfg)

    bad_regimes = {k for k, v in regime_trust.items() if v["sufficient"] and v["trust"] < 1.0}
    bad_symbols = {k for k, v in symbol_trust.items() if v["sufficient"] and v["trust"] < 1.0}
    bad_setups  = {k for k, v in setup_trust.items()  if v["sufficient"] and v["trust"] < 1.0}

    # Overtrading context: per-symbol counts + re-entry-after-loss within N days.
    symbol_counts = Counter(t["symbol"] for t in trades)
    reentry: set = set()
    by_symbol: Dict[str, List[dict]] = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t)
    for sym, ts in by_symbol.items():
        ts_sorted = sorted(ts, key=lambda x: x["entry_date"])
        last_loss_exit = None
        for t in ts_sorted:
            if last_loss_exit is not None:
                gap = (datetime.fromisoformat(t["entry_date"]).date()
                       - datetime.fromisoformat(last_loss_exit).date()).days
                if 0 <= gap <= cfg.reentry_days:
                    reentry.add(sym)
            if t["pnl"] < 0:
                last_loss_exit = t["exit_date"]

    ctx = {"bad_regimes": bad_regimes, "bad_symbols": bad_symbols, "bad_setups": bad_setups,
           "symbol_counts": symbol_counts, "reentry_after_loss": reentry}

    # Classify every LOSING trade.
    losers = [t for t in trades if t["pnl"] < 0]
    reason_counts: Counter = Counter()
    reason_loss: Counter = Counter()
    per_trade_reasons = []
    rejectable_pnl = 0.0       # pnl of ALL trades a pre-trade rule would have rejected
    rejected_losers = rejected_winners = 0
    rejected_loss_avoided = rejected_profit_foregone = 0.0
    for t in trades:
        rs = classify(t, ctx, cfg) if t["pnl"] < 0 else \
            [r for r in classify(t, ctx, cfg)]  # winners can still match pre-trade rules
        if t["pnl"] < 0:
            for r in rs:
                reason_counts[r] += 1
                reason_loss[r] += t["pnl"]
            per_trade_reasons.append((t, rs))
        # "Should have been rejected": any PRE-TRADE-knowable reason present.
        if PRE_TRADE_REASONS & set(rs):
            rejectable_pnl += t["pnl"]
            if t["pnl"] < 0:
                rejected_losers += 1
                rejected_loss_avoided += t["pnl"]
            elif t["pnl"] > 0:
                rejected_winners += 1
                rejected_profit_foregone += t["pnl"]

    # Repeated mistakes: symbols that lost repeatedly.
    repeated = []
    for sym, ts in by_symbol.items():
        sym_losers = [t for t in ts if t["pnl"] < 0]
        net = sum(t["pnl"] for t in ts)
        if len(sym_losers) >= 3 and net < 0:
            rc = Counter()
            for t in sym_losers:
                for r in classify(t, ctx, cfg):
                    rc[r] += 1
            repeated.append({"symbol": sym, "losses": len(sym_losers),
                             "net_pnl": round(net, 2),
                             "top_reason": rc.most_common(1)[0][0] if rc else "—"})
    repeated.sort(key=lambda x: x["net_pnl"])

    worst_symbols = [{"symbol": k, **v} for k, v in symbol_trust.items()][:8]
    worst_regimes = [{"regime": k, **v} for k, v in regime_trust.items()]

    # Diagnosis: is the loss SYSTEMIC (no edge anywhere) or SELECTIVE (some buckets ok)?
    suff_regimes = [k for k, v in regime_trust.items() if v["sufficient"]]
    suff_setups = [k for k, v in setup_trust.items() if v["sufficient"]]
    all_regimes_bad = bool(suff_regimes) and all(regime_trust[k]["trust"] < 1.0 for k in suff_regimes)
    all_setups_bad = bool(suff_setups) and all(setup_trust[k]["trust"] < 1.0 for k in suff_setups)
    systemic = all_regimes_bad and all_setups_bad

    # Router trust-gate simulation: apply the trust table the way the router would
    # (skip a trade when the combined down-only multiplier < gate_min). Demonstrates the
    # table avoiding bad trades on REAL journal data — no live change.
    gate_min = 0.50
    gate_trust = {"symbol": symbol_trust, "regime": regime_trust, "setup": setup_trust}
    kept = skipped = 0
    kept_pnl = skipped_pnl = 0.0
    for t in trades:
        m = lookup_trust(gate_trust, symbol=t["symbol"], regime=t["regime"],
                         setup=setup_of(t["entry_score"], cfg))
        if m < gate_min:
            skipped += 1
            skipped_pnl += t["pnl"]
        else:
            kept += 1
            kept_pnl += t["pnl"]
    router_gate = {
        "gate_min_trust": gate_min,
        "skipped": skipped, "skipped_net_pnl": round(skipped_pnl, 2),
        "kept": kept, "kept_net_pnl": round(kept_pnl, 2),
    }

    # Suggested next rule.
    if systemic:
        least_bad = max(regime_trust.items(), key=lambda kv: kv[1]["trust"])[0]
        suggestion = (
            "SYSTEMIC loss: the strategy is net-negative in EVERY regime and EVERY setup band. "
            "The trust table therefore down-weights across the board — effectively 'do not trade "
            "this strategy'. The bottleneck is the entry SIGNAL's lack of edge, not bucket "
            f"selection, so do NOT simply disable regimes. Least-bad regime = {least_bad}. "
            "Test next: fix/replace the entry signal (features or timeframe), or out-of-sample / "
            "walk-forward validate v_all before any deployment.")
    else:
        dominant = [r for r, _ in reason_counts.most_common() if r in PRE_TRADE_REASONS]
        suggestion = _suggest(dominant[0] if dominant else None, bad_regimes, bad_symbols, cfg)

    return {
        "diagnosis": "systemic" if systemic else "selective",
        "router_gate_simulation": router_gate,
        "total_trades": n,
        "losers": len(losers),
        "overall_avg_pnl": round(overall_avg, 2),
        "loss_reasons": [
            {"reason": r, "count": c, "loss": round(reason_loss[r], 2)}
            for r, c in reason_counts.most_common()
        ],
        "worst_symbols": worst_symbols,
        "worst_regimes": worst_regimes,
        "setup_breakdown": [{"setup": k, **v} for k, v in setup_trust.items()],
        "repeated_mistakes": repeated[:10],
        "should_have_been_rejected": {
            "rule": "reject any trade flagged with a pre-trade-knowable reason "
                    f"({sorted(PRE_TRADE_REASONS)})",
            "trades_rejected": rejected_losers + rejected_winners,
            "losers_rejected": rejected_losers,
            "winners_rejected": rejected_winners,
            "loss_avoided": round(rejected_loss_avoided, 2),
            "profit_foregone": round(rejected_profit_foregone, 2),
            "net_pnl_removed": round(rejectable_pnl, 2),
        },
        "suggested_rule_to_test_next": suggestion,
        "trust_tables": {
            "symbol": symbol_trust, "regime": regime_trust, "setup": setup_trust,
        },
    }


def _suggest(reason: Optional[str], bad_regimes, bad_symbols, cfg: MistakeConfig) -> str:
    if reason is None:
        return "No dominant pre-trade loss reason — gather more trades before changing rules."
    return {
        "weak_entry": f"Raise the BUY score threshold above {cfg.weak_entry_score:.2f} "
                      "(e.g. 0.70) and re-backtest; marginal signals dominate the losses.",
        "bad_regime": f"Skip or down-size entries when the index regime is in "
                      f"{sorted(bad_regimes)}; those regimes lose with sufficient sample.",
        "high_charges": "Add a min target/charge ratio gate (>= {:.0%}) and prefer wider "
                        "targets; charges are eating a large share of intended reward."
                        .format(cfg.high_charge_ratio),
        "bad_risk_reward": f"Require R:R >= {cfg.min_rr:.1f} (widen target or tighten entry); "
                           "sub-1.5R trades drag the book.",
        "bad_symbol": f"Down-weight the worst symbols {sorted(list(bad_symbols))[:5]} via the "
                      "trust table before adding any new symbols.",
        "bad_setup": "Require the 'strong' signal band; marginal setups underperform.",
    }.get(reason, f"Investigate '{reason}' as the dominant loss cause.")


# ── Strategy trust (across variant journals) ─────────────────────────────────
def strategy_trust(cfg: MistakeConfig = MistakeConfig()) -> dict:
    per: Dict[str, List[float]] = {}
    for db, label in STRATEGY_SOURCES:
        ts = load_trades(db)
        if ts:
            per[label] = [t["pnl"] for t in ts]
    if not per:
        return {}
    all_pnls = [p for v in per.values() for p in v]
    overall = sum(all_pnls) / len(all_pnls) if all_pnls else 0.0
    out = {}
    for label, pnls in per.items():
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        avg = sum(pnls) / n
        sufficient = n >= cfg.min_sample
        out[label] = {
            "trades": n, "win_rate": round(wins / n, 4), "net_pnl": round(sum(pnls), 2),
            "avg_pnl": round(avg, 2),
            "trust": _trust(avg, overall, cfg) if sufficient else 1.0,
            "sufficient": sufficient,
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["avg_pnl"]))


# ── Router-facing lookup (down-only) ─────────────────────────────────────────
def lookup_trust(trust: dict, *, symbol=None, regime=None, strategy=None, setup=None) -> float:
    """
    Most-conservative combined multiplier in [floor, 1.0] for the router.
    Returns the MIN of the applicable bucket trusts (missing buckets = 1.0 neutral).
    The router multiplies position size by this, or skips if below its own min_trust.
    It can only REDUCE exposure — never increase it.
    """
    vals = [1.0]
    for section, key in (("symbol", symbol), ("regime", regime),
                         ("strategy", strategy), ("setup", setup)):
        if key is not None:
            v = trust.get(section, {}).get(key)
            if isinstance(v, dict) and "trust" in v:
                vals.append(float(v["trust"]))
    return round(min(vals), 4)


# ── Orchestration ────────────────────────────────────────────────────────────
def run(backtest_db: str = "backtest_baseline.db",
        cfg: MistakeConfig = MistakeConfig()) -> dict:
    trades = load_trades(backtest_db)
    report = analyze(trades, cfg)
    report["strategy_trust"] = strategy_trust(cfg)
    report["paper_context"] = load_paper_context()

    trust_table = {
        "symbol":   report["trust_tables"]["symbol"],
        "regime":   report["trust_tables"]["regime"],
        "strategy": report["strategy_trust"],
        "setup":    report["trust_tables"]["setup"],
        "meta": {
            "source": backtest_db,
            "generated": datetime.now().isoformat(timespec="seconds"),
            "policy": "down-only [%.2f,1.0]; min_sample=%d; reduces bad trades only"
                      % (cfg.trust_floor, cfg.min_sample),
        },
    }
    TRUST_PATH.write_text(json.dumps(trust_table, indent=2, sort_keys=True), encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(report), encoding="utf-8")
    report["_trust_path"] = str(TRUST_PATH)
    report["_report_path"] = str(REPORT_PATH)
    return report


def render_markdown(r: dict) -> str:
    L = ["# Spencer — Mistake Review", ""]
    L.append(f"Closed trades analysed: **{r['total_trades']}** "
             f"(losers: {r['losers']}, avg P&L/trade: ₹{r['overall_avg_pnl']}).")
    L.append(f"\n**Diagnosis: {r.get('diagnosis', '?').upper()}** — "
             + ("net-negative in every regime AND setup; the trust table down-weights across "
                "the board (≈ stop trading this strategy). The fix is the entry SIGNAL, not "
                "bucket selection."
                if r.get("diagnosis") == "systemic" else
                "some buckets are worse than others; the trust table can steer away from them."))
    L.append("\n> Read-only post-mortem. Trust is **down-only** — it can shrink or skip "
             "trades, never increase risk. No live rules were changed.\n")

    L.append("## Top loss reasons")
    L.append("| reason | losing trades | loss (₹) |")
    L.append("|---|---:|---:|")
    for x in r["loss_reasons"]:
        L.append(f"| {x['reason']} | {x['count']} | {x['loss']:,.0f} |")

    L.append("\n## Worst symbols (lowest avg P&L)")
    L.append("| symbol | trades | win rate | net ₹ | trust |")
    L.append("|---|---:|---:|---:|---:|")
    for s in r["worst_symbols"]:
        L.append(f"| {s['symbol']} | {s['trades']} | {s['win_rate']:.0%} | "
                 f"{s['net_pnl']:,.0f} | {s['trust']} |")

    L.append("\n## Worst regimes")
    L.append("| regime | trades | win rate | net ₹ | trust |")
    L.append("|---|---:|---:|---:|---:|")
    for s in r["worst_regimes"]:
        L.append(f"| {s['regime']} | {s['trades']} | {s['win_rate']:.0%} | "
                 f"{s['net_pnl']:,.0f} | {s['trust']} |")

    L.append("\n## Worst strategies (across backtest variants)")
    L.append("| strategy | trades | win rate | net ₹ | trust |")
    L.append("|---|---:|---:|---:|---:|")
    for k, v in r.get("strategy_trust", {}).items():
        L.append(f"| {k} | {v['trades']} | {v['win_rate']:.0%} | {v['net_pnl']:,.0f} | {v['trust']} |")

    L.append("\n## Setup band breakdown")
    L.append("| setup | trades | win rate | net ₹ | trust |")
    L.append("|---|---:|---:|---:|---:|")
    for s in r["setup_breakdown"]:
        L.append(f"| {s['setup']} | {s['trades']} | {s['win_rate']:.0%} | "
                 f"{s['net_pnl']:,.0f} | {s['trust']} |")

    L.append("\n## Repeated mistakes (symbols that lost ≥3 times)")
    if r["repeated_mistakes"]:
        L.append("| symbol | losses | net ₹ | dominant reason |")
        L.append("|---|---:|---:|---|")
        for x in r["repeated_mistakes"]:
            L.append(f"| {x['symbol']} | {x['losses']} | {x['net_pnl']:,.0f} | {x['top_reason']} |")
    else:
        L.append("None.")

    sj = r["should_have_been_rejected"]
    L.append("\n## What should have been rejected")
    L.append(f"- Rule: {sj['rule']}")
    L.append(f"- Would reject **{sj['trades_rejected']}** trades "
             f"({sj['losers_rejected']} losers, {sj['winners_rejected']} winners).")
    L.append(f"- Loss avoided: **₹{sj['loss_avoided']:,.0f}**; profit foregone: "
             f"₹{sj['profit_foregone']:,.0f}; **net removed: ₹{sj['net_pnl_removed']:,.0f}**.")
    L.append("- (Honest caveat: this also removes some winners — the net is what matters.)")

    rg = r.get("router_gate_simulation", {})
    if rg:
        L.append("\n## Router trust-gate simulation (how the router would use the table)")
        L.append(f"- Skip a trade when combined down-only trust < {rg['gate_min_trust']:.2f} "
                 "(min of symbol/regime/setup trust).")
        L.append(f"- Would **skip {rg['skipped']}** trades (net ₹{rg['skipped_net_pnl']:,.0f}) "
                 f"and **keep {rg['kept']}** (net ₹{rg['kept_net_pnl']:,.0f}).")
        L.append("- The router only *reduces* trading here — it never adds risk.")

    L.append("\n## Rule change to test next (NOT applied)")
    L.append(f"> {r['suggested_rule_to_test_next']}")

    pc = r.get("paper_context", {})
    L.append(f"\n## Paper journal context\n- {pc.get('closed', 0)} closed paper trades. "
             f"{pc.get('note', '')}")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="bot.mistake_review")
    p.add_argument("--journal", default="backtest_baseline.db",
                   help="journal with the independent index regime (default)")
    args = p.parse_args(argv)
    report = run(args.journal)
    print(render_markdown(report))
    print(f"\nTrust table → {report['_trust_path']}")
    print(f"Report      → {report['_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
