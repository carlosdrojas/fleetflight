// Pure helpers that turn a trace (counterexample or replay) into drawable pieces.
// Nothing here knows about BMS/hub/inverter: lanes come from snapshot keys.
import type { Describe, SnapVal, TraceStep } from "./types";

export const DEFAULT_TICK_MS = 50;

export const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
export const str = (v: SnapVal | undefined): string => (v === null || v === undefined ? "" : String(v));

export const stepT = (s: TraceStep | undefined): number => num(s?.t_ms) ?? num(s?.snapshot?.t_ms) ?? 0;

export interface LaneDef { key: string; label: string }

/** Swimlanes: snapshot_keys with lane=true (describe order); otherwise every string-valued snapshot key. */
export function laneDefs(describe: Describe | null | undefined, trace: TraceStep[]): LaneDef[] {
  const keys = (describe?.snapshot_keys ?? []).filter((k) => k && typeof k.key === "string");
  const lanes = keys.filter((k) => k.lane).map((k) => ({ key: k.key as string, label: k.label || (k.key as string) }));
  if (lanes.length) return lanes;
  const first = trace.find((s) => s.snapshot)?.snapshot ?? {};
  return Object.keys(first)
    .filter((k) => k !== "t_ms" && (typeof first[k] === "string" || first[k] === undefined))
    .map((k) => ({ key: k, label: k }));
}

/** Every snapshot key to show in the state panel, labelled, describe order first. */
export function stateKeys(describe: Describe | null | undefined, trace: TraceStep[]): LaneDef[] {
  const out: LaneDef[] = [];
  const seen = new Set<string>(["t_ms"]);
  for (const k of describe?.snapshot_keys ?? []) {
    if (k?.key && !seen.has(k.key)) {
      seen.add(k.key);
      out.push({ key: k.key, label: k.label || k.key });
    }
  }
  for (const s of trace) {
    for (const k of Object.keys(s.snapshot ?? {})) {
      if (!seen.has(k)) {
        seen.add(k);
        out.push({ key: k, label: k });
      }
    }
  }
  return out;
}

export interface Segment {
  value: string;
  start_ms: number;
  end_ms: number;
  firstStep: number; // index into trace
  lastStep: number;
}

/** Group consecutive steps with the same value of `key`. A segment ends where the next begins. */
export function segments(trace: TraceStep[], key: string, endMs?: number): Segment[] {
  const out: Segment[] = [];
  trace.forEach((s, i) => {
    const v = str(s.snapshot?.[key]);
    const t = stepT(s);
    const last = out[out.length - 1];
    if (last && last.value === v) {
      last.lastStep = i;
      return;
    }
    if (last) last.end_ms = t;
    out.push({ value: v, start_ms: t, end_ms: t, firstStep: i, lastStep: i });
  });
  const tail = out[out.length - 1];
  if (tail) tail.end_ms = Math.max(tail.start_ms, endMs ?? stepT(trace[trace.length - 1]));
  return out;
}

export interface TimerWindow { start_ms: number; end_ms: number; open: boolean; firstStep: number; lastStep: number }

/** Maximal stretches where snapshot[timerKey] is non-null (CONTRACT §4 "Windows"). */
export function timerWindows(trace: TraceStep[], timerKey: string): TimerWindow[] {
  const out: TimerWindow[] = [];
  let cur: TimerWindow | null = null;
  trace.forEach((s, i) => {
    const v = num(s.snapshot?.[timerKey]);
    if (v !== null) {
      if (!cur || cur.start_ms !== v) {
        if (cur) {
          cur.end_ms = stepT(s);
          cur.open = false;
          out.push(cur);
        }
        cur = { start_ms: v, end_ms: stepT(s), open: true, firstStep: i, lastStep: i };
      } else {
        cur.end_ms = stepT(s);
        cur.lastStep = i;
      }
    } else if (cur) {
      cur.end_ms = stepT(s);
      cur.open = false;
      out.push(cur);
      cur = null;
    }
  });
  if (cur) out.push(cur);
  return out;
}

export type Tone = "fail" | "warn" | "pass" | "accent" | "neutral" | "empty";

const TONES: [Tone, RegExp][] = [
  ["fail", /^(FAULT|FAULTED|ERROR|TRIP|TRIPPED|ALARM|FAILED|FAIL)$/],
  ["warn", /^(RESTART|RESTARTING|DEGRADED|BOOT|BOOTING|UNKNOWN|TIMEOUT|LOST|STALE|WARN)$/],
  ["pass", /^(HEALTHY|ONLINE|OK|READY|NORMAL|PASS)$/],
  ["neutral", /^(IDLE|SHUTDOWN|OFF|STOPPED|STANDBY|NONE|-|—)$/],
  ["accent", /^(DISCHARGING|CHARGING|ACTIVE|RUNNING|ON)$/],
];

/** Colour a state value by its first word. Unknown words are shown as neutral info, never guessed. */
export function tone(value: string): Tone {
  const v = value.trim();
  if (!v) return "empty";
  const head = v.split(/[\s·,(]/)[0].toUpperCase();
  for (const [t, re] of TONES) if (re.test(head)) return t;
  return "accent";
}

/** Lane an injected move acts on, by naming convention (`bms_fault` → bms). null when no lane matches. */
export function moveLane(moveName: string | undefined, lanes: LaneDef[]): string | null {
  if (!moveName) return null;
  const hit = lanes.find((l) => moveName === l.key || moveName.startsWith(`${l.key}_`));
  return hit ? hit.key : null;
}

/** Evenly spaced axis ticks, at most `maxTicks`, on a 1/2/2.5/5 × 10^n grid. */
export function niceTicks(endMs: number, maxTicks = 12): number[] {
  const end = Math.max(1, endMs);
  const raw = end / maxTicks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let t = 0; t <= end + 1e-9; t += step) out.push(Math.round(t));
  return out;
}

export type TraceRow =
  | { kind: "step"; index: number }
  | { kind: "gap"; from: number; to: number; count: number };

/** A step is worth a row if something visible happens: init, injections, events, violations, lane changes, last step. */
export function isInteresting(trace: TraceStep[], i: number, laneKeys: string[]): boolean {
  const s = trace[i];
  if (i === 0 || i === trace.length - 1) return true;
  if (s.move?.injected) return true;
  if ((s.events ?? []).length) return true;
  if ((s.violations ?? []).length) return true;
  const prev = trace[i - 1];
  return laneKeys.some((k) => str(prev?.snapshot?.[k]) !== str(s.snapshot?.[k]));
}

/** Collapse runs of plain ticks into one "gap" row. `keep` forces a step to stay visible (e.g. the cursor). */
export function collapseTrace(trace: TraceStep[], laneKeys: string[], keep: number | null = null): TraceRow[] {
  const rows: TraceRow[] = [];
  let gapStart = -1;
  const flush = (end: number) => {
    if (gapStart < 0) return;
    const count = end - gapStart;
    if (count === 1) rows.push({ kind: "step", index: gapStart });
    else rows.push({ kind: "gap", from: gapStart, to: end - 1, count });
    gapStart = -1;
  };
  trace.forEach((_, i) => {
    if (i === keep || isInteresting(trace, i, laneKeys)) {
      flush(i);
      rows.push({ kind: "step", index: i });
    } else if (gapStart < 0) gapStart = i;
  });
  flush(trace.length);
  return rows;
}

/** One-line description of what a step did, from its move and events. */
export function stepSummary(s: TraceStep): string {
  const ev = (s.events ?? []).filter((e) => !e.injected).map((e) => e.detail || e.name).filter(Boolean);
  if (ev.length) return ev.join(" · ");
  if (s.move?.injected) return "chosen by the adversary";
  return "";
}

export function moveText(s: TraceStep): string {
  if (!s.move) return "init";
  return s.move.label || s.move.name || "?";
}

/** Keys whose value differs from the previous step. */
export function changedKeys(trace: TraceStep[], i: number): Set<string> {
  const out = new Set<string>();
  if (i <= 0) return out;
  const a = trace[i - 1]?.snapshot ?? {};
  const b = trace[i]?.snapshot ?? {};
  for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
    if (k !== "t_ms" && str(a[k]) !== str(b[k])) out.add(k);
  }
  return out;
}

export function shortHash(h: string | undefined | null): string {
  if (!h) return "—";
  const [algo, hex] = h.includes(":") ? h.split(":", 2) : ["", h];
  return `${algo ? algo + ":" : ""}${hex.slice(0, 12)}`;
}

export const fmtInt = (v: unknown): string => {
  const n = num(v);
  return n === null ? "—" : Math.round(n).toLocaleString("en-US");
};

export const fmtCompact = (v: unknown): string => {
  const n = num(v);
  if (n === null) return "—";
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  return Math.round(n).toLocaleString("en-US");
};

export const fmtMs = (v: unknown): string => {
  const n = num(v);
  return n === null ? "—" : `${n.toLocaleString("en-US")} ms`;
};

export const fmtSec = (v: unknown): string | null => {
  const n = num(v);
  if (n === null) return null;
  return n >= 10 ? `${n.toFixed(1)} s` : n >= 1 ? `${n.toFixed(2)} s` : `${Math.round(n * 1000)} ms`;
};

export function fmtDuration(ms: number): string {
  if (ms >= 1000 && ms % 100 === 0) return `${ms / 1000} s`;
  return `${ms} ms`;
}

export function splitAssumption(s: string): [string, string] {
  const m = /^(ASSUMED|OUT OF SCOPE)\s+(.*)$/s.exec(s ?? "");
  return m ? [m[1], m[2]] : ["", s ?? ""];
}

export const sutVersion = (id: string | undefined): string => (id ? (id.includes("@") ? id.split("@")[1] : id) : "—");
