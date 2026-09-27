import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import type { InvariantDef, TraceStep } from "../lib/types";
import { moveLane, moveText, niceTicks, num, segments, stepT, timerWindows, tone, type LaneDef, type Tone } from "../lib/trace";

const TONE: Record<Tone, { fill: string; stroke: string; text: string }> = {
  fail: { fill: "#2A1614", stroke: "#FF6B57", text: "#FF8A7A" },
  warn: { fill: "#2A2213", stroke: "#E5A63A", text: "#E5A63A" },
  pass: { fill: "#15291F", stroke: "#3DBE8B", text: "#3DBE8B" },
  accent: { fill: "#18243B", stroke: "#7AA2FF", text: "#9DBBFF" },
  neutral: { fill: "#1A1F27", stroke: "#4A5362", text: "#C9CFD8" },
  empty: { fill: "none", stroke: "#2A3240", text: "#8C96A5" },
};

export interface SwimlaneProps {
  trace: TraceStep[];
  lanes: LaneDef[];
  cursor: number;
  onPick: (index: number) => void;
  invariant?: InvariantDef | null;
  violatedAtMs?: number | null;
  timerLabel?: string;
  /** Steps to flag as diverging (replay). */
  diverged?: Set<number>;
}

const LABEL_W = 112;
const RIGHT = 20;
const TOP = 30;
const LANE_H = 54;
const RECT_Y = 16;
const RECT_H = 30;
const TIMER_H = 44;
const AXIS_H = 26;

export default function Swimlane({ trace, lanes, cursor, onPick, invariant, violatedAtMs, timerLabel, diverged }: SwimlaneProps) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1100);
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(600, Math.floor(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const lastT = stepT(trace[trace.length - 1]);
  const timerKey = invariant?.timer_key || null;
  const bound = num(invariant?.bound_ms);
  const windows = useMemo(() => (timerKey ? timerWindows(trace, timerKey) : []), [trace, timerKey]);
  // The window live at the violating (last) step sets the deadline.
  const lastWin = windows.find((w) => w.lastStep === trace.length - 1) ?? windows[windows.length - 1];
  const deadline = lastWin && bound !== null ? lastWin.start_ms + bound : null;
  const endMs = Math.max(lastT, deadline ?? 0, 1);
  const ticks = niceTicks(endMs, Math.max(4, Math.floor((width - LABEL_W) / 90)));
  const axisEnd = Math.max(endMs, ticks[ticks.length - 1]);

  const x0 = LABEL_W;
  const x1 = width - RIGHT;
  const x = (t: number) => x0 + (Math.max(0, Math.min(t, axisEnd)) / axisEnd) * (x1 - x0);
  const laneY = (i: number) => TOP + i * LANE_H;
  const timerY = TOP + lanes.length * LANE_H;
  const bottom = timerY + (timerKey ? TIMER_H : 0);
  const H = bottom + AXIS_H;

  const segs = useMemo(() => lanes.map((l) => segments(trace, l.key)), [trace, lanes]);

  // Lanes named in the invariant's formula are the ones the violation is about.
  const formula = invariant?.formula ?? "";
  const hot = new Set(lanes.filter((l) => new RegExp(`\\b${l.key.replace(/[^\w]/g, "")}\\b`).test(formula)).map((l) => l.key));
  const violT = num(violatedAtMs);

  // Injected moves, grouped by (lane, t).
  const injections = useMemo(() => {
    const groups = new Map<string, { lane: number; t: number; labels: string[]; steps: number[] }>();
    trace.forEach((s, i) => {
      if (!s.move?.injected) return;
      const lk = moveLane(s.move.name, lanes);
      const li = lk ? lanes.findIndex((l) => l.key === lk) : -1;
      const t = stepT(s);
      const k = `${li}@${t}`;
      const g = groups.get(k) ?? { lane: li, t, labels: [], steps: [] };
      g.labels.push(moveText(s));
      g.steps.push(i);
      groups.set(k, g);
    });
    return [...groups.values()];
  }, [trace, lanes]);

  const cur = trace[Math.max(0, Math.min(cursor, trace.length - 1))];
  const cx = x(stepT(cur));

  const pickAt = (e: MouseEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * width;
    if (px < x0 - 8) return;
    const t = ((px - x0) / (x1 - x0)) * axisEnd;
    // Last step at or before t; clicking again on the same time walks through steps that share it.
    let best = 0;
    trace.forEach((s, i) => {
      if (stepT(s) <= t + 1e-6) best = i;
    });
    const sameT = trace.map((s, i) => [stepT(s), i] as const).filter(([st]) => st === stepT(trace[best])).map(([, i]) => i);
    if (sameT.includes(cursor) && sameT.length > 1) {
      const next = sameT[(sameT.indexOf(cursor) + 1) % sameT.length];
      onPick(next);
    } else onPick(best);
  };

  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight") {
      onPick(Math.min(trace.length - 1, cursor + 1));
      e.preventDefault();
    } else if (e.key === "ArrowLeft") {
      onPick(Math.max(0, cursor - 1));
      e.preventDefault();
    }
  };

  const clip = (s: string, w: number, fs = 12) => {
    const max = Math.floor((w - 16) / (fs * 0.61));
    if (max < 2) return "";
    return s.length > max ? s.slice(0, Math.max(1, max - 1)) + "…" : s;
  };

  return (
    <div ref={wrap} tabIndex={0} onKeyDown={onKey} aria-label="Swimlane timeline. Use left and right arrow keys to step." style={{ outline: "none" }}>
      <svg className="lane-svg" width={width} height={H} viewBox={`0 0 ${width} ${H}`} role="img" aria-label={`Timeline of ${trace.length} steps across ${lanes.map((l) => l.label).join(", ")}`} onClick={pickAt}>
        <defs>
          <pattern id="ff-hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="3" height="8" fill="#FF6B57" opacity="0.6" />
          </pattern>
        </defs>

        {/* grid + axis */}
        <g stroke="#1F2630">
          {ticks.map((t) => (
            <line key={t} x1={x(t)} y1={TOP - 6} x2={x(t)} y2={bottom} />
          ))}
        </g>
        <g fill="#8C96A5" fontSize={11} textAnchor="middle">
          {ticks.map((t, i) => (
            <text key={t} x={x(t)} y={bottom + 18} textAnchor={i === ticks.length - 1 ? "end" : "middle"}>
              {t}
            </text>
          ))}
        </g>

        <text x={x1} y={bottom + 18} fill="#8C96A5" fontSize={11} textAnchor="end">
          {x(ticks[ticks.length - 1]) < x1 - 40 ? "ms" : ""}
        </text>

        {/* lanes */}
        {lanes.map((l, li) => {
          const y = laneY(li);
          return (
            <g key={l.key}>
              <text x={0} y={y + RECT_Y + 20} fill="#E7EAEE" fontSize={13} fontWeight={600}>
                {l.label.length > 12 ? l.label.slice(0, 11) + "…" : l.label}
              </text>
              <line x1={x0} y1={y + RECT_Y + RECT_H / 2} x2={x1} y2={y + RECT_Y + RECT_H / 2} stroke="#2A3240" strokeDasharray="3 5" />
              {segs[li].map((s, si) => {
                const tn = tone(s.value);
                if (tn === "empty") return null;
                const c = TONE[tn];
                const sx = x(s.start_ms);
                const w = Math.max(3, x(s.end_ms) - sx - 2);
                const active = cursor >= s.firstStep && cursor <= s.lastStep;
                return (
                  <g key={si} className="hit">
                    <title>{`${l.label}: ${s.value}\n${s.start_ms}–${s.end_ms} ms · steps ${s.firstStep}–${s.lastStep}`}</title>
                    <rect x={sx + 1} y={y + RECT_Y} width={w} height={RECT_H} rx={6} fill={c.fill} stroke={c.stroke} strokeWidth={active ? 2 : 1} />
                    <text x={sx + 11} y={y + RECT_Y + 20} fill={c.text} fontSize={12} fontWeight={600}>
                      {clip(s.value, w)}
                    </text>
                  </g>
                );
              })}
              {/* violation hatch on the lanes the invariant talks about */}
              {deadline !== null && violT !== null && violT > deadline && (hot.size === 0 || hot.has(l.key)) && (
                <rect x={x(deadline)} y={y + RECT_Y} width={Math.max(2, x(violT) - x(deadline))} height={RECT_H} fill="url(#ff-hatch)" pointerEvents="none" />
              )}
            </g>
          );
        })}

        {/* timer lane: the invariant's bounded window vs its budget */}
        {timerKey && (
          <g>
            <text x={0} y={timerY + 24} fill="#E7EAEE" fontSize={13} fontWeight={600}>
              {(timerLabel ?? timerKey).slice(0, 12)}
            </text>
            <text x={0} y={timerY + 40} fill="#8C96A5" fontSize={10}>
              {bound !== null ? `budget ${bound} ms` : "window"}
            </text>
            <line x1={x0} y1={timerY + 22} x2={x1} y2={timerY + 22} stroke="#2A3240" strokeDasharray="3 5" />
            {windows.length === 0 && (
              <text x={x0 + 8} y={timerY + 26} fill="#8C96A5" fontSize={11}>
                timer never started
              </text>
            )}
            {windows.map((w, wi) => {
              const end = w.end_ms;
              const okEnd = bound !== null ? Math.min(end, w.start_ms + bound) : end;
              const dur = end - w.start_ms;
              const over = bound !== null && dur > bound;
              return (
                <g key={wi}>
                  <title>{`${timerKey}: ${w.start_ms}–${end} ms (${dur} ms${w.open ? ", still open" : ""})${bound !== null ? ` · budget ${bound} ms` : ""}`}</title>
                  <rect x={x(w.start_ms)} y={timerY + 12} width={Math.max(2, x(okEnd) - x(w.start_ms))} height={20} rx={4} fill="#2F4A7A" />
                  {over && <rect x={x(w.start_ms + (bound as number))} y={timerY + 12} width={Math.max(2, x(end) - x(w.start_ms + (bound as number)))} height={20} fill="#FF6B57" opacity={0.75} />}
                  <text x={x(w.start_ms) + 8} y={timerY + 26} fill="#E7EAEE" fontSize={11} fontWeight={600}>
                    {clip(`${dur} ms${bound !== null ? (over ? ` · ${dur - bound} over budget` : ` · ${bound - dur} headroom`) : ""}`, x(end) - x(w.start_ms) + 30, 11)}
                  </text>
                </g>
              );
            })}
          </g>
        )}

        {/* deadline */}
        {deadline !== null && (
          <g pointerEvents="none">
            <line x1={x(deadline)} y1={12} x2={x(deadline)} y2={bottom} stroke="#FF6B57" strokeWidth={1.5} strokeDasharray="5 4" />
            <text x={x(deadline) + (x(deadline) > x1 - 260 ? -8 : 8)} y={16} fill="#FF8A7A" fontSize={11} textAnchor={x(deadline) > x1 - 260 ? "end" : "start"}>
              deadline · {timerKey} + {bound} ms = {deadline} ms
            </text>
          </g>
        )}

        {/* injected moves */}
        {injections.map((g, gi) => {
          const gx = x(g.t);
          const y = g.lane >= 0 ? laneY(g.lane) + RECT_Y - 5 : TOP - 10;
          const label = `⚡ ${g.labels.join(" + ")}`;
          const room = x1 - gx - 12;
          const selected = g.steps.includes(cursor);
          return (
            <g key={gi} className="hit" onClick={(e) => { e.stopPropagation(); onPick(g.steps[selected ? (g.steps.indexOf(cursor) + 1) % g.steps.length : 0]); }}>
              <title>{`injected at ${g.t} ms: ${g.labels.join(", ")}`}</title>
              <path d={`M${gx} ${y - 5} l5 5 l-5 5 l-5 -5 z`} fill="#E5A63A" stroke="#0D1015" strokeWidth={1} />
              <text x={gx + 9} y={y + 3} fill="#E5A63A" fontSize={11} fontWeight={600}>
                {clip(label, room + 16, 11)}
              </text>
            </g>
          );
        })}

        {/* replay divergence ticks */}
        {diverged &&
          [...diverged].map((i) => (
            <line key={i} x1={x(stepT(trace[i]))} y1={bottom - 4} x2={x(stepT(trace[i]))} y2={bottom + 4} stroke="#FF6B57" strokeWidth={2} />
          ))}

        {/* violation marker */}
        {violT !== null && (
          <g pointerEvents="none">
            <circle cx={x(violT)} cy={bottom} r={4} fill="#FF6B57" />
          </g>
        )}

        {/* cursor */}
        <g pointerEvents="none">
          <line x1={cx} y1={TOP - 8} x2={cx} y2={bottom} stroke="#E7EAEE" strokeWidth={2} />
          <circle cx={cx} cy={TOP - 8} r={5} fill="#E7EAEE" />
        </g>
      </svg>
    </div>
  );
}
