import { useEffect, useMemo, useRef, useState } from "react";
import type { Shared } from "../App";
import { Empty, ErrorState, Loading, PlayIcon, Result } from "../components/ui";
import { api } from "../lib/api";
import { href, useAsync, useFixtureFlag, useHeader } from "../lib/hooks";
import type { Counterexample, ReplayResult, TraceStep } from "../lib/types";
import { collapseTrace, laneDefs, moveText, num, shortHash, stepT, sutVersion, type TraceRow } from "../lib/trace";

export default function ReplayScreen({ shared, cexId }: { shared: Shared; cexId: string | null }) {
  const cex = useAsync(() => api.cex(cexId as string), cexId);
  useFixtureFlag("cex", cex.data);
  if (!cexId) return <Empty>No counterexample to replay. Pick one from Checks.</Empty>;
  if (cex.error) return <ErrorState title={`Could not load ${cexId}`} error={cex.error} onRetry={cex.reload} />;
  if (!cex.data) return <Loading lines={6} />;
  return <ReplayView shared={shared} cex={cex.data} cexId={cexId} />;
}

function ReplayView({ shared, cex, cexId }: { shared: Shared; cex: Counterexample; cexId: string }) {
  const versions = useMemo(() => {
    const v = [...(shared.describe?.sut_versions ?? [])];
    if (cex.sut?.id && !v.includes(cex.sut.id)) v.unshift(cex.sut.id);
    return v;
  }, [shared.describe, cex]);
  const [sut, setSut] = useState(cex.sut?.id ?? versions[0] ?? "");
  const [key, setKey] = useState<string | null>(sut ? `${cexId}|${sut}|0` : null);
  const replay = useAsync(() => api.replay(cexId, key!.split("|")[1]), key);
  useFixtureFlag("replay", replay.data);
  useHeader(`replay / ${cexId}`, replay.data?.sut?.id ?? sut);

  const run = () => setKey(`${cexId}|${sut}|${Date.now()}`);

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <h1>Replay {cexId}</h1>
          <span className="muted">
            The simulator applies the counterexample's {(cex.moves ?? []).length} injected moves through the same transition code, against the SUT you pick.
          </span>
        </div>
        <div className="ph-actions">
          <label className="small muted" htmlFor="sut">
            SUT
          </label>
          <select id="sut" value={sut} onChange={(e) => setSut(e.target.value)}>
            {versions.map((v) => (
              <option key={v} value={v}>
                {sutVersion(v)}
                {v === cex.sut?.id ? " (found on)" : ""}
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={run} disabled={!sut || replay.loading}>
            <PlayIcon />
            {replay.loading ? "Replaying…" : "Replay"}
          </button>
          <a className="btn btn-primary" href={href("versions", cexId)}>
            Try every version →
          </a>
        </div>
      </div>

      {replay.error && <ErrorState title={`Replay against ${sutVersion(sut)} failed`} error={replay.error} onRetry={run} />}
      {replay.loading && !replay.data && <Loading lines={4} />}
      {replay.data && <ReplayBody shared={shared} cex={cex} r={replay.data} determinism={<Determinism cexId={cexId} sut={replay.data.sut?.id ?? sut} first={replay.data} />} />}
    </>
  );
}

function ReplayBody({ shared, cex, r, determinism }: { shared: Shared; cex: Counterexample; r: ReplayResult; determinism: React.ReactNode }) {
  const ctrace: TraceStep[] = (cex.trace ?? []).filter(Boolean);
  const steps = (r.steps ?? []).filter(Boolean);
  const compared = num(r.compared_steps) ?? Math.min(ctrace.length, steps.length);
  const lanes = laneDefs(shared.describe, ctrace).map((l) => l.key);
  const diverged = steps.map((s, i) => (s.match === false ? i : -1)).filter((i) => i >= 0);
  const rows = collapseTrace(ctrace.slice(0, compared), lanes);
  // Keep diverging steps visible even if the checker trace considers them idle.
  const shown = new Set(rows.flatMap((x) => (x.kind === "step" ? [x.index] : [])));
  const allRows = rows.flatMap((x): TraceRow[] => {
    if (x.kind === "step") return [x];
    const inner = diverged.filter((i) => i >= x.from && i <= x.to && !shown.has(i));
    return inner.length ? Array.from({ length: x.to - x.from + 1 }, (_, k) => ({ kind: "step" as const, index: x.from + k })) : [x];
  });
  const vw = r.violation_window_ms;
  const failing = (r.invariants ?? []).filter((i) => i?.result === "FAIL");
  const invId = cex.invariant?.id;
  const cexInv = (r.invariants ?? []).find((i) => i?.id === invId);
  const extra = Math.max(0, steps.length - compared);

  return (
    <>
      <div className={`banner ${r.hash_match ? "ok" : r.same_sut === false ? "warn" : "bad"}`}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={r.hash_match ? "#3DBE8B" : r.same_sut === false ? "#E5A63A" : "#FF6B57"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          {r.hash_match ? <path d="m8 12 3 3 5-6" /> : <path d="M12 7v6M12 16.5h.01" />}
        </svg>
        <span style={{ fontWeight: 600 }}>
          {r.hash_match ? "Trace hashes identical" : r.same_sut === false ? `Trace diverges at step ${r.first_divergence ?? "?"} (expected: different SUT)` : `Trace diverges at step ${r.first_divergence ?? "?"}`}
        </span>
        <span className="mono" style={{ fontSize: 13, color: "var(--text2)" }}>
          checker {shortHash(r.expected_trace_hash)} {r.hash_match ? "=" : "≠"} simulator {shortHash(r.trace_hash)}
        </span>
        <span className="mono" style={{ marginLeft: "auto", fontSize: 13, fontWeight: 600, color: r.verdict === "PASS" ? "var(--pass)" : "var(--fail-text)" }}>
          {cexInv?.result === "FAIL"
            ? `${invId} still FAILS${num(cexInv.first_violation_ms) !== null ? ` at t = ${cexInv.first_violation_ms} ms` : ""}`
            : r.verdict === "PASS"
              ? "all invariants pass"
              : `${failing.map((f) => f.id).join(", ")} fail`}
        </span>
      </div>

      {(r.skipped_moves ?? []).length > 0 && (
        <div className="banner warn" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
          <b className="t-warn">Skipped moves: not enabled on {sutVersion(r.sut?.id)}, so not forced</b>
          {(r.skipped_moves ?? []).map((m, i) => (
            <span key={i} className="mono small">
              tick {m.tick_index}: {m.move?.label ?? m.move?.name} ({m.reason})
            </span>
          ))}
        </div>
      )}

      <div className="grid2">
        <Column title="Checker" sub={`counterexample · ${cex.sut?.id ?? "?"}`} rows={allRows} steps={ctrace} />
        <Column title="Simulator" sub={`executes ${r.sut?.id ?? "?"} · ${r.matched_steps ?? "?"}/${compared} steps match`} rows={allRows} steps={steps} match={(i) => steps[i]?.match} diff={(i) => steps[i]?.diff ?? []} />
      </div>

      {determinism}

      <section className="card">
        <div className="card-h">
          <b>Invariants over the whole replay</b>
          <span className="sub">
            {steps.length} steps to {num(r.horizon_ms) ?? "?"} ms{extra ? ` (${extra} past the counterexample)` : ""}
          </span>
          <span className="right">
            <Result r={r.verdict} />
          </span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 10 }}>
          {(r.invariants ?? []).map((iv, i) => (
            <div key={iv?.id ?? i} style={{ border: `1px solid ${iv?.result === "FAIL" ? "#5a2a24" : "var(--line)"}`, borderRadius: 8, padding: "8px 12px" }}>
              <div className="mono" style={{ display: "flex", gap: 8, fontSize: 13 }}>
                <b>{iv?.id}</b>
                <span style={{ marginLeft: "auto" }}>
                  <Result r={iv?.result} />
                </span>
              </div>
              <div className="mono small muted">
                {iv?.max_window ? `longest window ${iv.max_window.duration_ms} ms${iv.max_window.open ? " (open)" : ""}` : iv?.first_violation_ms != null ? `first violation ${iv.first_violation_ms} ms` : "no timer window"}
              </div>
            </div>
          ))}
        </div>
        {vw && (
          <span className="small muted mono">
            {vw.invariant} window {vw.start_ms}→{vw.end_ms ?? "open"} ms = {vw.duration_ms} ms vs budget {vw.bound_ms} ms ({(vw.over_budget_ms ?? 0) > 0 ? `${vw.over_budget_ms} ms over` : `${-(vw.over_budget_ms ?? 0)} ms headroom`})
          </span>
        )}
      </section>
    </>
  );
}


function Column({ title, sub, rows, steps, match, diff }: { title: string; sub: string; rows: TraceRow[]; steps: TraceStep[]; match?: (i: number) => boolean | null | undefined; diff?: (i: number) => string[] }) {
  return (
    <section className="card" style={{ gap: 2 }}>
      <div className="card-h" style={{ marginBottom: 8 }}>
        <b>{title}</b>
        <span className="sub">{sub}</span>
      </div>
      {rows.map((row) => {
        if (row.kind === "gap")
          return (
            <div key={`g${row.from}`} className="mono faint" style={{ fontSize: 12, padding: "4px 0 4px 40px", borderBottom: "1px solid var(--grid)" }}>
              ··· {row.count} ticks
            </div>
          );
        const s = steps[row.index];
        const m = match?.(row.index);
        const d = diff?.(row.index) ?? [];
        const injected = !!s?.move?.injected;
        const viol = (s?.violations ?? []).length > 0;
        return (
          <div key={row.index} className="mono" style={{ display: "grid", gridTemplateColumns: match ? "30px 60px minmax(0, 1fr) 24px" : "30px 60px minmax(0, 1fr)", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--grid)", fontSize: 13, alignItems: "baseline" }}>
            <span className="faint">{row.index}</span>
            <span className="muted">{s ? stepT(s) : "—"}</span>
            <span style={{ color: viol ? "var(--fail-text)" : injected ? "var(--warn)" : undefined, fontWeight: viol ? 600 : undefined, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={s ? moveText(s) : ""}>
              {!s ? <span className="faint">missing</span> : viol && !injected ? `✕ ${(s.violations ?? []).join(", ")} violated` : `${moveText(s)}${injected ? "*" : ""}`}
              {d.length > 0 && <span className="t-fail small"> · differs: {d.join(", ")}</span>}
            </span>
            {match && <span style={{ color: m === true ? "var(--pass)" : m === false ? "var(--fail-text)" : "var(--faint)" }} aria-label={m === true ? "match" : m === false ? "mismatch" : "not compared"}>{m === true ? "✓" : m === false ? "✕" : "·"}</span>}
          </div>
        );
      })}
    </section>
  );
}

type Cell = { hash: string | null; verdict?: string; error?: string };

function Determinism({ cexId, sut, first }: { cexId: string; sut: string; first: ReplayResult }) {
  const [n, setN] = useState(50);
  const [cells, setCells] = useState<Cell[]>([]);
  const [running, setRunning] = useState(false);
  const cancel = useRef(false);
  useEffect(() => () => void (cancel.current = true), []);
  useEffect(() => setCells([]), [cexId, sut]);

  const ref = first.full_trace_hash ?? null;
  const go = async () => {
    const total = Math.max(1, Math.min(500, Math.floor(n) || 1));
    cancel.current = false;
    setRunning(true);
    setCells([]);
    let next = 0;
    const worker = async () => {
      while (!cancel.current && next < total) {
        const i = next++;
        let cell: Cell;
        try {
          const r = await api.replay(cexId, sut);
          cell = { hash: r.full_trace_hash ?? null, verdict: r.verdict };
        } catch (e) {
          cell = { hash: null, error: (e as Error).message };
        }
        setCells((c) => {
          const out = c.slice();
          out[i] = cell;
          return out;
        });
      }
    };
    await Promise.all([worker(), worker(), worker(), worker()]);
    setRunning(false);
  };

  const done = cells.filter(Boolean);
  const same = done.filter((c) => c.hash && c.hash === ref).length;
  const counts = new Map<string, { n: number; verdict: string }>();
  for (const c of done) {
    const k = c.hash ? shortHash(c.hash) : `error: ${c.error}`;
    counts.set(k, { n: (counts.get(k)?.n ?? 0) + 1, verdict: c.verdict ?? "" });
  }
  const total = running ? Math.max(done.length, Math.floor(n)) : cells.length;

  return (
    <div className="grid2">
      <section className="card">
        <div className="card-h">
          <b>Determinism</b>
          <span className="sub">each cell is one full replay to the horizon, compared by full_trace_hash</span>
          {done.length > 0 && (
            <span className="right mono" style={{ fontSize: 13, color: same === done.length ? "var(--pass)" : "var(--fail-text)" }}>
              {same} / {done.length} identical
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <label htmlFor="rep-n" className="small muted">
            Repeat ×
          </label>
          <input id="rep-n" type="number" min={1} max={500} value={n} onChange={(e) => setN(Number(e.target.value))} style={{ width: 90, height: 32 }} />
          <button type="button" className="btn btn-sm" onClick={go} disabled={running}>
            {running ? `Running ${done.length}/${total}…` : `Repeat ×${Math.max(1, Math.min(500, Math.floor(n) || 1))}`}
          </button>
          {running && (
            <button type="button" className="btn btn-sm" onClick={() => (cancel.current = true)}>
              Stop
            </button>
          )}
        </div>
        {total > 0 ? (
          <div className="det-grid" role="img" aria-label={`${same} of ${done.length} replays produced the same hash`}>
            {Array.from({ length: total }, (_, i) => {
              const c = cells[i];
              const cls = !c ? "" : c.error ? "err" : c.hash === ref ? "same" : "diff";
              return <span key={i} className={cls} title={c ? (c.error ?? shortHash(c.hash)) : "pending"} />;
            })}
          </div>
        ) : (
          <span className="small muted">Runs the same replay N times through the API. Any differing hash would show red.</span>
        )}
      </section>
      <section className="card card-code">
        <div className="code">
          <div>
            <span className="p">$</span> fleetflight replay --counterexample {cexId} \
          </div>
          <div>
            {"    "}--sut {sutVersion(sut)} --repeat {done.length || "N"} | uniq -c
          </div>
          {done.length === 0 && <div className="p"># press Repeat to fill this in from real API responses</div>}
          {[...counts.entries()].map(([h, c]) => (
            <div key={h}>
              {String(c.n).padStart(7)} {h} <span style={{ color: c.verdict === "PASS" ? "var(--pass)" : "var(--fail-text)" }}>{c.verdict}</span>
            </div>
          ))}
          <div className="p" style={{ marginTop: 8 }}># UI equivalent of the CLI command; counts come from {done.length} POST /api/replay calls</div>
        </div>
      </section>
    </div>
  );
}
