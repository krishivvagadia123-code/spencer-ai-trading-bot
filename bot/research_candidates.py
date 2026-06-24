"""Declarative candidate schema for RELIANCE intraday research.

Candidates are data, not code. Rules are a small JSON-like expression language
over current or past candles/indicators so a candidate cannot smuggle in
look-ahead, callbacks, or subjective judgment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ALLOWED_SYMBOL = "RELIANCE"
ALLOWED_INTERVALS = {"1m", "15m"}
CAPITAL_BASIS_INR = 5_000.0
ALLOWED_SIDES = {"LONG", "SHORT"}
EXECUTION_ASSUMPTION = {
    "entry_fill": "next_candle_open",
    "exit_fill": "next_candle_open",
}
ALLOWED_CONTEXT_FIELDS = frozenset({
    "prev_session_range_pct",
    "prev_session_close",
    "gap_pct",
    "session_minute",
    "is_expiry_session",
})
FORBIDDEN_RULE_KEYS = {
    "callback",
    "callable",
    "eval",
    "exec",
    "function",
    "future",
    "future_candle",
    "lookahead",
    "next",
    "python",
}
REQUIRED_FIELDS = {
    "id",
    "version",
    "hypothesis",
    "symbol",
    "interval",
    "entry_rule",
    "exit_rule",
    "stop_rule",
    "sizing_rule",
    "no_trade_conditions",
    "execution_assumption",
    "parameters",
    "capital",
    "max_open_positions",
}
FrozenJson = Any


def _deep_freeze(value: Any) -> FrozenJson:
    if isinstance(value, dict):
        return tuple((str(k), _deep_freeze(v)) for k, v in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(v) for v in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise ValueError(f"candidate contains non-declarative value: {type(value).__name__}")


def _unfreeze(value: FrozenJson) -> Any:
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
            return {key: _unfreeze(val) for key, val in value}
        return [_unfreeze(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _walk_rule(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_rule(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_rule(child)


def _validate_no_future_references(rule: Any, path: str = "rule") -> None:
    for node in _walk_rule(rule):
        if not isinstance(node, dict):
            continue
        for raw_key, raw_value in node.items():
            key = str(raw_key)
            key_l = key.lower()
            if key_l in FORBIDDEN_RULE_KEYS:
                raise ValueError(f"{path} references forbidden future/callback key: {key}")
            if isinstance(raw_value, str) and "future" in raw_value.lower():
                raise ValueError(f"{path} references future data: {raw_value}")
            if key_l == "context":
                context_name = str(raw_value)
                if context_name not in ALLOWED_CONTEXT_FIELDS:
                    raise ValueError(f"{path} references unknown context field: {context_name}")
            if key_l in {"offset", "periods", "shift"}:
                try:
                    amount = int(raw_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{path}.{key} must be an integer") from exc
                if amount < 0:
                    raise ValueError(f"{path}.{key} cannot point into the future")
            if key_l == "window":
                try:
                    window = int(raw_value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{path}.window must be an integer") from exc
                if window <= 0:
                    raise ValueError(f"{path}.window must be positive")


@dataclass(frozen=True)
class ResearchCandidate:
    id: str
    version: str
    hypothesis: str
    symbol: str
    interval: str
    entry_rule: FrozenJson
    exit_rule: FrozenJson
    stop_rule: FrozenJson
    sizing_rule: FrozenJson
    no_trade_conditions: tuple[FrozenJson, ...]
    execution_assumption: FrozenJson
    parameters: FrozenJson
    capital: float = CAPITAL_BASIS_INR
    max_open_positions: int = 1
    side: str = "LONG"
    tunable_parameters: tuple[str, ...] = field(default_factory=tuple)

    @property
    def params_hash(self) -> str:
        return _hash_json(self.parameters_dict)

    @property
    def hypothesis_hash(self) -> str:
        return hashlib.sha256(self.hypothesis.strip().encode("utf-8")).hexdigest()

    @property
    def canonical_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "hypothesis": self.hypothesis,
            "symbol": self.symbol,
            "interval": self.interval,
            "entry_rule": _unfreeze(self.entry_rule),
            "exit_rule": _unfreeze(self.exit_rule),
            "stop_rule": _unfreeze(self.stop_rule),
            "sizing_rule": _unfreeze(self.sizing_rule),
            "no_trade_conditions": [_unfreeze(item) for item in self.no_trade_conditions],
            "execution_assumption": _unfreeze(self.execution_assumption),
            "parameters": _unfreeze(self.parameters),
            "capital": self.capital,
            "max_open_positions": self.max_open_positions,
            "side": self.side,
            "tunable_parameters": list(self.tunable_parameters),
        }

    @property
    def parameters_dict(self) -> dict:
        return _unfreeze(self.parameters)

    def to_json(self) -> str:
        return _canonical_json(self.canonical_dict)


def candidate_from_dict(data: dict) -> ResearchCandidate:
    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise ValueError(f"candidate missing required fields: {', '.join(sorted(missing))}")

    symbol = str(data["symbol"]).upper()
    if symbol != ALLOWED_SYMBOL:
        raise ValueError(f"candidate symbol must be {ALLOWED_SYMBOL}, got {symbol}")

    interval = str(data["interval"])
    if interval not in ALLOWED_INTERVALS:
        raise ValueError(f"candidate interval must be one of {sorted(ALLOWED_INTERVALS)}, got {interval}")

    capital = float(data["capital"])
    if capital != CAPITAL_BASIS_INR:
        raise ValueError(f"candidate capital must be {CAPITAL_BASIS_INR}, got {capital}")

    max_open_positions = int(data["max_open_positions"])
    if max_open_positions != 1:
        raise ValueError("candidate max_open_positions must be exactly 1")

    side = str(data.get("side", "LONG")).upper()
    if side not in ALLOWED_SIDES:
        raise ValueError(f"candidate side must be one of {sorted(ALLOWED_SIDES)}, got {side}")

    assumption = dict(data["execution_assumption"])
    if assumption != EXECUTION_ASSUMPTION:
        raise ValueError(f"execution_assumption must be {EXECUTION_ASSUMPTION}")

    if not str(data["id"]).strip():
        raise ValueError("candidate id is required")
    if not str(data["version"]).strip():
        raise ValueError("candidate version is required")
    if not str(data["hypothesis"]).strip():
        raise ValueError("candidate hypothesis is required")
    if not isinstance(data["parameters"], dict):
        raise ValueError("candidate parameters must be an object")
    if not isinstance(data["no_trade_conditions"], list):
        raise ValueError("candidate no_trade_conditions must be a list")

    for name in ("entry_rule", "exit_rule", "stop_rule", "sizing_rule"):
        _validate_no_future_references(data[name], name)
    for idx, rule in enumerate(data["no_trade_conditions"]):
        _validate_no_future_references(rule, f"no_trade_conditions[{idx}]")

    return ResearchCandidate(
        id=str(data["id"]).strip(),
        version=str(data["version"]).strip(),
        hypothesis=str(data["hypothesis"]).strip(),
        symbol=symbol,
        interval=interval,
        entry_rule=_deep_freeze(data["entry_rule"]),
        exit_rule=_deep_freeze(data["exit_rule"]),
        stop_rule=_deep_freeze(data["stop_rule"]),
        sizing_rule=_deep_freeze(data["sizing_rule"]),
        no_trade_conditions=tuple(_deep_freeze(item) for item in data["no_trade_conditions"]),
        execution_assumption=_deep_freeze(assumption),
        parameters=_deep_freeze(data["parameters"]),
        capital=capital,
        max_open_positions=max_open_positions,
        side=side,
        tunable_parameters=tuple(str(item) for item in data.get("tunable_parameters", [])),
    )


def load_candidate(path: str | Path) -> ResearchCandidate:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("candidate file must contain a JSON object")
    return candidate_from_dict(data)


def candidate_hash(candidate: ResearchCandidate) -> str:
    return _hash_json(candidate.canonical_dict)


def rule_to_dict(rule: FrozenJson) -> Any:
    return _unfreeze(rule)
