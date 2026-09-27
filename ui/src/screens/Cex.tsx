import { useEffect, useMemo, useState } from "react";
import type { Shared } from "../App";
import Swimlane from "../components/Swimlane";
import { StatePanel, TraceList } from "../components/TracePanels";
import { Empty, ErrorState, Loading, PlayIcon } from "../components/ui";
import { api } from "../lib/api";
import { href, useAsync, useFixtureFlag, useHeader } from "../lib/hooks";
import type { Counterexample } from "../lib/types";
import { laneDefs, num, shortHash, stateKeys } from "../lib/trace";

export default function CexScreen({ shared, cexId }: { shared: Shared; cexId: string | null }) {
  const cex = useAsync(() => api.cex(cexId as string), cexId);
  useFixtureFlag("cex", cex.data);
  useHeader(cexId ? `counterexamples / ${cexId}` : "counterexamples", cex.data?.sut?.id ?? null);

  if (!cexId) {
    if (shared.runsError) return <ErrorState title="Could not load runs" error={shared.runsError} onRetry={shared.reload} />;
    if (!shared.runs) return <Loading />;
    return <Empty>No counterexamples in any run. Every checked invariant held within bounds.</Empty>;
  }
  if (cex.error) return <ErrorState title={`Could not load ${cexId}`} error={cex.error} onRetry={cex.reload} />;
  if (!cex.data) return <Loading lines={6} />;
  return <CexView shared={shared} cex={cex.data} />;
}

function CexView({ shared, cex }: { shared: Shared; cex: Counterexample }) {
  const trace = useMemo(() => (Array.isArray(cex.trace) ? cex.trace.filter(Boolean) : []), [cex]);
  const lanes = useMemo(() => laneDefs(shared.describe, trace), [shared.describe, trace]);
  const keys = useMemo(() => stateKeys(shared.describe, trace), [shared.describe, trace]);
  const laneKeys = useMemo(() => lanes.map((l) => l.key), [lanes]);
  const [cursor, setCursor] = useState(Math.max(0, trace.length - 1));
  const id = cex.id ?? "counterexample";
  const inv = cex.invariant ?? null;
  const injected = trace.filter((s) => s.move?.injected).length;
  const timerLabel = shared.describe?.snapshot_keys?.find((k) => k?.key === inv?.timer_key)?.label;

  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || e.defaultPrevented) return;
      if (e.key === "ArrowRight") setCursor((c) => Math.min(trace.length - 1, c + 1));
      else if (e.key === "ArrowLeft") setCursor((c) => Math.max(0, c - 1));
      else if (e.key === "Home") setCursor(0);
      else if (e.key === "End") setCursor(trace.length - 1);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [trace.length]);

  const download = () => {
    const blob = new Blob([JSON.stringify(cex, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  const sub = [
    cex.search?.minimal ? "minimal (BFS)" : cex.search ? "not proven minimal" : null,
    num(cex.search?.depth) !== null ? `${cex.search?.depth} moves` : `${Math.max(0, trace.length - 1)} moves`,
    `${injected} injected`,
    num(cex.violated_at_ms) !== null ? `violated at ${cex.violated_at_ms} ms` : null,
  ].filter(Boolean);

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <div className="ph-title">
            <h1>{id}</h1>
            {inv && (
              <span className="chip-fail" title={inv.formula}>
                {inv.id} {inv.name}
              </span>
            )}
            {shared.cexIds.length > 1 && (
              <select aria-label="Counterexample" value={id} onChange={(e) => (window.location.hash = href("cex", e.target.value))} style={{ height: 30 }}>
                {[...new Set([...shared.cexIds, id])].map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            )}
          </div>
          {cex.explanation && <span className="muted">{cex.explanation}</span>}
          <span className="muted small">{sub.join(" · ")}</span>
          <span className="mono faint small">
            found on {cex.sut?.id ?? "?"} · trace {shortHash(cex.trace_hash)}
            {num(cex.search?.states_explored) !== null && ` · ${cex.search?.states_explored?.toLocaleString("en-US")} states explored`}
          </span>
        </div>
        <div className="ph-actions">
          <button type="button" className="btn" onClick={download}>
            Download .json
          </button>
          <a className="btn" href={href("regress", id)}>
            Regression test
          </a>
          <a className="btn btn-primary" href={href("replay", id)}>
            <PlayIcon />
            Replay in simulator
          </a>
        </div>
      </div>

      {trace.length === 0 ? (
        <Empty>This counterexample has no trace steps.</Empty>
      ) : (
        <>
          <section className="card lane-card">
            {lanes.length === 0 ? (
              <span className="muted">No swimlane keys: describe has no snapshot_keys with lane=true and the snapshots have no string values.</span>
            ) : (
              <Swimlane trace={trace} lanes={lanes} cursor={cursor} onPick={setCursor} invariant={inv} violatedAtMs={cex.violated_at_ms} timerLabel={timerLabel} />
            )}
          </section>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)", gridTemplateRows: "minmax(0, 1fr)", gap: 18, minHeight: 300, flex: "1 1 0" }}>
            <TraceList trace={trace} laneKeys={laneKeys} cursor={cursor} onPick={setCursor} failStep={trace.length - 1} />
            <StatePanel trace={trace} index={cursor} keys={keys} note={cursor === trace.length - 1 && inv ? violationNote(cex) : null} />
          </div>
        </>
      )}
    </>
  );
}

function violationNote(cex: Counterexample): string {
  const inv = cex.invariant;
  const parts = [`Violation of ${inv?.id ?? "the invariant"}: ${inv?.description ?? inv?.formula ?? ""}`];
  if (num(cex.violation_duration_ms) !== null && num(inv?.bound_ms) !== null)
    parts.push(`The condition has held for ${cex.violation_duration_ms} ms against a ${inv?.bound_ms} ms bound.`);
  return parts.join(" ");
}
