import { useState } from "react";
import { Database, Link2, RefreshCw, Save, Search } from "lucide-react";
import { ObsidianBrainGraph } from "../components/ObsidianBrainGraph";
import { StatusCard } from "../components/StatusCard";
import { useObsidianBrain } from "../hooks/useObsidianBrain";
import { displayName, fmtIST, isMissing, money, pct } from "../utils/helpers";

const researchValue = (value, formatter = (next) => next) =>
  isMissing(value) ? "N/A" : formatter(value);

function MarketResearchPanel({ row, status, loadResearch, botState }) {
  if (status === "loading") return <StatusCard title="Loading Brain Data" message="Analyzing latest backend state..." />;
  if (status === "error" || status === "disconnected") return <StatusCard title="Connection Error" message="Could not reach the Brain module." />;
  if (status === "empty" || !row) return <StatusCard title="No Data" message="No active brain research row." />;

  const regimes = Object.values(botState?.regimeTrust?.regimes || {});
  const source = row.source || "Backend research endpoint";

  return (
    <div className="liquid-glass-light rounded-[24px] p-6 text-[var(--color-primary-dark-text)] sm:p-8">
      <div className="mb-12 border-b border-[var(--color-light-border)] pb-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-3xl font-light tracking-tight">{row.symbol || "RELIANCE"}</h2>
            <div className="mt-2 font-mono text-sm text-[var(--color-muted-dark-text)]">{fmtIST(row.asof)}</div>
          </div>
          <div className="rounded-full border border-black/10 bg-black/[0.03] px-4 py-2 font-mono text-xs text-black/55">
            {source}
          </div>
        </div>
      </div>

      <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Trend</div>
          <div className="font-mono text-xl capitalize">{row.trend || "N/A"}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Last Price</div>
          <div className="font-mono text-xl">{researchValue(row.lastPrice, (value) => money(value, 2))}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">SMA 20</div>
          <div className="font-mono text-xl">{researchValue(row.sma20, (value) => money(value, 2))}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">SMA 50</div>
          <div className="font-mono text-xl">{researchValue(row.sma50, (value) => money(value, 2))}</div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Return 20d</div>
          <div className="font-mono text-xl">
            {researchValue(row.return20d, (value) => pct(Number(value) * 100))}
          </div>
        </div>
      </div>

      <div className="mt-12 rounded-xl bg-black/[0.03] p-6">
        <div className="mb-4 text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Verified Reading</div>
        <p className="leading-relaxed text-black/65">
          The backend classifies the current trend as <span className="text-black/85">{row.trend || "unavailable"}</span>.
          This is a descriptive market snapshot from {source}; it is not a validated edge or trade instruction.
        </p>
      </div>

      <div className="mt-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-widest text-[var(--color-muted-dark-text)]">Regime Trust</div>
            <p className="mt-2 text-sm text-[var(--theme-muted)]">Historical backend evidence by market regime.</p>
          </div>
          {botState?.regimeTrust?.last_updated && (
            <div className="max-w-full break-words text-right font-mono text-xs text-[var(--theme-muted)]">
              Updated {fmtIST(botState.regimeTrust.last_updated)}
            </div>
          )}
        </div>

        {regimes.length ? (
          <div className="grid gap-3 md:grid-cols-3">
            {regimes.map((regime) => (
              <div key={regime.regime} className="page-subcard rounded-2xl p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">{displayName(regime.regime)}</span>
                  <span className="font-mono text-sm text-[var(--theme-text)]">{pct(Number(regime.trust) * 100, 1)} trust</span>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-3 font-mono text-xs">
                  <div>
                    <div className="text-[var(--theme-muted)]">Trades</div>
                    <div className="mt-1 text-[var(--theme-text)]">{regime.trades ?? "N/A"}</div>
                  </div>
                  <div>
                    <div className="text-[var(--theme-muted)]">Win rate</div>
                    <div className="mt-1 text-[var(--theme-text)]">{pct(Number(regime.win_rate) * 100, 1)}</div>
                  </div>
                  <div>
                    <div className="text-[var(--theme-muted)]">Net PnL</div>
                    <div className="mt-1 text-[var(--theme-text)]">{money(regime.net_pnl, 2)}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="page-subcard rounded-2xl p-5 text-sm">
            No regime-trust evidence is currently available from the backend.
          </p>
        )}
      </div>

      <button type="button" onClick={loadResearch} className="mt-8 rounded-lg bg-[var(--color-primary-black)] px-6 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90">
        Refresh Analysis
      </button>
    </div>
  );
}

function PrimaryBrainPanel() {
  const {
    brainStatus,
    graph,
    results,
    status,
    message,
    search,
    capture,
    reindex,
  } = useObsidianBrain();
  const [query, setQuery] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("memory");
  const [saving, setSaving] = useState(false);

  const submitSearch = (event) => {
    event.preventDefault();
    search(query);
  };

  const submitCapture = async (event) => {
    event.preventDefault();
    if (!title.trim() || !content.trim()) return;
    setSaving(true);
    try {
      await capture({ title, content, kind });
      setTitle("");
      setContent("");
    } catch {
      // The hook surfaces the error next to the capture form.
    } finally {
      setSaving(false);
    }
  };

  const metrics = [
    ["Notes", brainStatus?.noteCount],
    ["Generated", brainStatus?.generatedCount],
    ["Manual memory", brainStatus?.memoryCount],
    ["References", brainStatus?.referenceCount],
    ["Links", brainStatus?.linkCount],
    ["Broken links", brainStatus?.brokenLinkCount],
  ];

  return (
    <div className="liquid-glass-light rounded-[24px] p-6 text-[var(--color-primary-dark-text)] sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-black/10 pb-7">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-black/45">
            <Database className="h-4 w-4" />
            Primary memory
          </div>
          <h2 className="mt-3 text-3xl font-light tracking-tight">Obsidian Brain</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-black/55">
            Spencer searches this vault before answering. Generated truth refreshes from the journal and repo;
            operator memories remain reviewable and are never overwritten.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-emerald-900/10 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-800">
            {brainStatus?.primary ? "Primary brain active" : status === "error" ? "Unavailable" : "Checking"}
          </span>
          <button
            type="button"
            onClick={reindex}
            className="rounded-full border border-black/10 p-2 text-black/55 transition hover:bg-black/[0.04]"
            title="Rebuild brain index"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-7 overflow-hidden rounded-[24px] border border-white/65 bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
        <ObsidianBrainGraph graph={graph} />
      </div>

      <div className="mt-7 grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-black/10 bg-black/[0.025] p-4">
            <div className="text-[11px] uppercase tracking-wider text-black/40">{label}</div>
            <div className="mt-2 font-mono text-xl text-black/75">{value ?? "N/A"}</div>
          </div>
        ))}
      </div>

      <div className="mt-8 grid gap-8 xl:grid-cols-[1.3fr_0.7fr]">
        <div>
          <form onSubmit={submitSearch} className="flex gap-2">
            <div className="flex flex-1 items-center rounded-xl border border-black/10 bg-white/55 px-4">
              <Search className="h-4 w-4 text-black/35" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="w-full bg-transparent px-3 py-3 text-sm outline-none"
                placeholder="Ask what Spencer knows, decided, tested, or cannot prove..."
              />
            </div>
            <button className="rounded-xl bg-black px-5 text-sm font-medium text-white">
              Search
            </button>
          </form>

          <div className="mt-4 space-y-3">
            {results.map((result) => (
              <article key={result.path} className="rounded-2xl border border-black/10 bg-white/45 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-medium text-black/80">{result.title}</h3>
                  <span className="font-mono text-[11px] text-black/40">{result.wikilink}</span>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-black/55">{result.snippet}</p>
                <div className="mt-3 flex items-center gap-2 text-[11px] text-black/35">
                  <Link2 className="h-3.5 w-3.5" />
                  {result.path}
                </div>
              </article>
            ))}
            {!results.length && (
              <div className="rounded-2xl border border-dashed border-black/10 p-8 text-center text-sm text-black/40">
                Search results will appear here with Obsidian citations.
              </div>
            )}
          </div>
        </div>

        <form onSubmit={submitCapture} className="rounded-2xl border border-black/10 bg-black/[0.025] p-5">
          <div className="flex items-center gap-2 text-sm font-medium text-black/75">
            <Save className="h-4 w-4" />
            Capture for review
          </div>
          <p className="mt-2 text-xs leading-relaxed text-black/45">
            New notes enter the manual memory inbox as unverified. They do not change trading authority.
          </p>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value)}
            className="mt-5 w-full rounded-xl border border-black/10 bg-white/60 px-3 py-2.5 text-sm outline-none"
          >
            {["memory", "decision", "lesson", "question", "task", "session", "observation"].map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className="mt-3 w-full rounded-xl border border-black/10 bg-white/60 px-3 py-2.5 text-sm outline-none"
            placeholder="Memory title"
          />
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            className="mt-3 min-h-32 w-full resize-y rounded-xl border border-black/10 bg-white/60 px-3 py-2.5 text-sm outline-none"
            placeholder="Verified fact, decision, lesson, or open question..."
          />
          <button
            disabled={saving || !title.trim() || !content.trim()}
            className="mt-3 w-full rounded-xl bg-black px-4 py-2.5 text-sm font-medium text-white disabled:opacity-35"
          >
            {saving ? "Capturing..." : "Add to Obsidian inbox"}
          </button>
          {message && <p className="mt-3 text-xs leading-relaxed text-black/50">{message}</p>}
        </form>
      </div>
    </div>
  );
}

export function Brain(props) {
  return (
    <div className="space-y-8">
      <PrimaryBrainPanel />
      <MarketResearchPanel {...props} />
    </div>
  );
}
