import { useEffect, useMemo, useRef, useState } from "react";
import type { TraceStep } from "../lib/types";
import { changedKeys, collapseTrace, moveText, stepSummary, stepT, str, type LaneDef } from "../lib/trace";

export function TraceList({
  trace,
  laneKeys,
  cursor,
  onPick,
  failStep,
  marks,
}: {
  trace: TraceStep[];
  laneKeys: string[];
  cursor: number;
  onPick: (i: number) => void;
  failStep?: number | null;
  /** Optional per-step suffix (e.g. replay ✓/✕). */
  marks?: (i: number) => React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const rows = useMemo(() => (expanded ? trace.map((_, i) => ({ kind: "step" as const, index: i })) : collapseTrace(trace, laneKeys, cursor)), [trace, laneKeys, cursor, expanded]);
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Scroll only the list, never the page.
    const list = listRef.current;
    const el = list?.querySelector<HTMLElement>('[aria-current="step"]');
    if (!list || !el) return;
    const top = el.offsetTop;
    if (top < list.scrollTop) list.scrollTop = top;
    else if (top + el.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top + el.offsetHeight - list.clientHeight;
  }, [cursor]);
  const hidden = rows.reduce((n, r) => n + (r.kind === "gap" ? r.count : 0), 0);

  return (
    <section className="card" style={{ padding: 12, gap: 4, minHeight: 0 }}>
      <div className="card-h" style={{ padding: "4px 8px 8px" }}>
        <b>Trace</b>
        <span className="sub">
          · {trace.length} steps · click a step or use <span className="kbd">←</span> <span className="kbd">→</span>
        </span>
        <button type="button" className="btn btn-sm right" onClick={() => setExpanded((e) => !e)} aria-pressed={expanded}>
          {expanded ? "Collapse idle ticks" : hidden ? `Show all (${hidden} idle)` : "Show all"}
        </button>
      </div>
      <div className="trace-list" ref={listRef}>
        {rows.map((r) => {
          if (r.kind === "gap")
            return (
              <button key={`g${r.from}`} type="button" className="gap-btn" onClick={() => onPick(r.from)} title={`steps ${r.from}–${r.to}`}>
                ··· {r.count} ticks, no lane change ({stepT(trace[r.from])}–{stepT(trace[r.to])} ms)
              </button>
            );
          const i = r.index;
          const s = trace[i];
          const injected = !!s.move?.injected;
          const viol = (s.violations ?? []).length > 0 || i === failStep;
          const color = viol ? "var(--fail-text)" : injected ? "var(--warn)" : "var(--text)";
          const ev = viol && !injected && s.move?.name === "tick" ? `✕ ${(s.violations ?? []).join(", ") || "violation"}` : `${moveText(s)}${injected ? "*" : ""}`;
          return (
            <button key={i} type="button" className="trace-btn" aria-current={i === cursor ? "step" : undefined} onClick={() => onPick(i)}>
              <span className="n">{i}</span>
              <span className="t">{stepT(s)} ms</span>
              <span className="ev" style={{ color }} title={moveText(s)}>
                {ev}
              </span>
              <span className="sum" title={stepSummary(s)}>
                {stepSummary(s) || (i === 0 ? "initial state" : "")}
                {marks && <span style={{ float: "right" }}>{marks(i)}</span>}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function StatePanel({ trace, index, keys, note }: { trace: TraceStep[]; index: number; keys: LaneDef[]; note?: string | null }) {
  const s = trace[index];
  if (!s) return null;
  const changed = changedKeys(trace, index);
  const events = (s.events ?? []).filter(Boolean);
  const viol = (s.violations ?? []).filter(Boolean);
  return (
    <section className="card" style={{ minHeight: 0, overflow: "auto" }}>
      <div className="card-h">
        <b>State at step {index}</b>
        <span className="mono sub">t = {stepT(s)} ms</span>
        <span className="mono sub right" style={{ color: s.move?.injected ? "var(--warn)" : undefined }}>
          move: {moveText(s)}
          {s.move?.injected ? " · injected" : ""}
        </span>
      </div>
      {(events.length > 0 || viol.length > 0 || note) && (
        <div style={{ borderBottom: "1px solid var(--line)", paddingBottom: 12, display: "flex", flexDirection: "column", gap: 6 }}>
          {!note && viol.map((v) => (
            <div key={v} className="mono t-fail" style={{ fontWeight: 600, fontSize: 13 }}>
              ✕ {v} violated in this state
            </div>
          ))}
          {events.map((e, i) => (
            <div key={i} className="mono" style={{ fontSize: 13, color: e.injected ? "var(--warn)" : "var(--text2)" }}>
              {e.injected ? "⚡ " : "→ "}
              {e.detail || e.name}
            </div>
          ))}
          {note && <div style={{ color: "var(--text2)", lineHeight: 1.5 }}>{note}</div>}
        </div>
      )}
      <div className="kv">
        {keys.map((k) => {
          const v = s.snapshot?.[k.key];
          return [
            <span key={`k${k.key}`} className="k" title={k.label}>
              {k.label}
            </span>,
            <span key={`v${k.key}`} className={`v${changed.has(k.key) ? " changed" : ""}`} title={changed.has(k.key) ? `changed from ${str(trace[index - 1]?.snapshot?.[k.key]) || "∅"}` : undefined}>
              {v === null || v === undefined || v === "" ? <span className="faint">∅</span> : String(v)}
              {changed.has(k.key) && " ●"}
            </span>,
          ];
        })}
      </div>
    </section>
  );
}
