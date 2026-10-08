import type { ReplayResult, TraceEvent, TraceStep } from "./types";
import { num } from "./trace";

// Turns a replay trace into what the 3D scene draws at any time t: component states,
// messages in flight on the wires, the invariant timer and plain-English captions.
// Everything here is derived from the trace; the scene invents no behaviour of its own.

export type NodeId = "bms" | "hub" | "inv";

export interface Flight {
  id: string;
  kind: string; // FAULT, ACK, CMD
  label: string; // what the packet says: FAULT, ACK, STOP, 5 kW
  from: NodeId;
  to: NodeId;
  t0: number;
  t1: number;
  fate: "deliver" | "lost" | "pending";
  delayed: boolean;
}

export interface Frame {
  t: number;
  bms: string;
  hub: string;
  inv: string;
  link: string;
  timerSince: number | null;
  violations: string[];
}

export interface Caption {
  t: number;
  text: string;
  tone: "info" | "warn" | "fail" | "pass";
}

export interface Timeline {
  frames: Frame[];
  flights: Flight[];
  captions: Caption[];
  endMs: number;
  /** First time any invariant is violated, if ever. */
  violationAt: number | null;
  violated: string[];
}

/** Visual length of a message that is dropped the instant it is sent. */
export const LOST_FLIGHT_MS = 40;

const NODES: Record<string, NodeId> = { bms: "bms", hub: "hub", inv: "inv" };
const SEND_RE = /^(\S+)\s+(\w+)\s+(\w+)→(\w+)(.*)$/;
const DELIVER_RE = /^(\S+)\s+→\s+(\w+)/;

function packetLabel(kind: string, rest: string): string {
  if (kind !== "CMD") return kind;
  if (/\bSTOP\b/.test(rest)) return "STOP";
  const w = rest.match(/(\d+)W\b/);
  if (w) return Number(w[1]) >= 1000 ? `${Number(w[1]) / 1000} kW` : `${w[1]} W`;
  return "CMD";
}

const str = (v: unknown) => (typeof v === "string" ? v : v == null ? "" : String(v));

function caption(e: TraceEvent, f: Flight | undefined): Omit<Caption, "t"> | null {
  const d = str(e.detail);
  switch (e.name) {
    case "bms_fault":
      return { text: "BMS detects a cell fault", tone: "warn" };
    case "network_loss":
      return { text: "Hub ↔ inverter link goes down", tone: "warn" };
    case "hub_restart":
      return { text: "Hub restarts", tone: "warn" };
    case "hub_boot":
      return { text: `Hub back up (${d.replace(/^hub up as /, "")})`, tone: "info" };
    case "bus_delay":
    case "delayed":
      return e.name === "delayed" ? { text: `${d.split(" ")[0]} held on the bus until ${d.split(" ").pop()} ms`, tone: "warn" } : null;
    case "send":
      return f ? { text: `${nodeName(f.from)} sends ${f.label} to ${nodeName(f.to)}`, tone: "info" } : null;
    case "deliver":
      return f && f.kind !== "CMD" ? { text: `${f.label} reaches the ${nodeName(f.to).toLowerCase()}`, tone: "info" } : null;
    case "lost":
      return f && f.label === "STOP" ? { text: `STOP to inverter lost (link down)`, tone: "fail" } : null;
    case "inv_mode":
    case "inv_reapply":
      return { text: d.charAt(0).toUpperCase() + d.slice(1), tone: /SHUTDOWN|IDLE/.test(d) ? "pass" : "warn" };
    default:
      return null;
  }
}

export function nodeName(n: NodeId): string {
  return n === "bms" ? "BMS" : n === "hub" ? "Hub" : "Inverter";
}

export function buildTimeline(r: ReplayResult, timerKey: string | null | undefined, tailMs = 450): Timeline {
  const steps: TraceStep[] = (r.steps ?? []).filter((s): s is TraceStep => !!s);
  const frames: Frame[] = [];
  const byId = new Map<string, Flight>();
  const flights: Flight[] = [];
  const captions: Caption[] = [];
  let violationAt: number | null = null;
  const violated = new Set<string>();
  let lastInteresting = 0;
  let lostStopCaptioned = false;

  for (const s of steps) {
    const t = num(s.t_ms) ?? 0;
    const snap = s.snapshot ?? {};
    const viol = (s.violations ?? []).filter((v): v is string => typeof v === "string");
    frames.push({
      t,
      bms: str(snap.bms),
      hub: str(snap.hub),
      inv: str(snap.inv),
      link: str(snap.link) || "UP",
      timerSince: timerKey ? num(snap[timerKey]) : null,
      violations: viol,
    });
    if (viol.length && violationAt === null) {
      violationAt = t;
      captions.push({ t, text: `${viol.join(", ")} violated`, tone: "fail" });
      lastInteresting = t;
    }
    viol.forEach((v) => violated.add(v));

    for (const e of s.events ?? []) {
      if (!e) continue;
      const d = str(e.detail);
      let f: Flight | undefined;
      if (e.name === "send" || e.name === "refresh" || e.name === "lost") {
        const m = d.match(SEND_RE);
        if (m && NODES[m[3]] && NODES[m[4]]) {
          f = byId.get(m[1]);
          if (!f) {
            f = { id: m[1], kind: m[2], label: packetLabel(m[2], m[5]), from: NODES[m[3]], to: NODES[m[4]], t0: t, t1: t, fate: "pending", delayed: false };
            byId.set(f.id, f);
            flights.push(f);
          }
          if (e.name === "lost") {
            f.fate = "lost";
            f.t1 = Math.max(t, f.t0 + LOST_FLIGHT_MS);
          }
        }
      } else if (e.name === "deliver") {
        const m = d.match(DELIVER_RE);
        f = m ? byId.get(m[1]) : undefined;
        if (f) {
          f.fate = "deliver";
          f.t1 = t;
        }
      } else if (e.name === "delayed") {
        const id = d.split(" ")[0];
        const g = byId.get(id);
        if (g) g.delayed = true;
      }
      // One "STOP lost" caption is the story; the retries every 100 ms would drown the log.
      if (e.name === "lost" && f?.label === "STOP") {
        if (lostStopCaptioned) continue;
        lostStopCaptioned = true;
      }
      const c = caption(e, f);
      if (c) {
        captions.push({ t, ...c });
        if (e.name !== "lost" && e.name !== "send" && e.name !== "deliver") lastInteresting = t;
      }
    }
  }

  const horizon = num(r.horizon_ms) ?? frames[frames.length - 1]?.t ?? 0;
  const windowEnd = num(r.violation_window_ms?.end_ms) ?? 0;
  for (const f of flights) if (f.fate === "pending") f.t1 = horizon;
  const endMs = Math.min(horizon, Math.max(lastInteresting, windowEnd, violationAt ?? 0) + tailMs);
  return { frames, flights, captions, endMs, violationAt, violated: [...violated] };
}

/** The last frame at or before t (several steps can share a t_ms; the last one wins). */
export function frameAt(tl: Timeline, t: number): Frame | null {
  let lo = 0;
  let hi = tl.frames.length - 1;
  let best = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (tl.frames[mid].t <= t) {
      best = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return best < 0 ? tl.frames[0] ?? null : tl.frames[best];
}

/** Where a flight is at time t: 0..1 along its wire, or null when it isn't on the wire. */
export function flightProgress(f: Flight, t: number): number | null {
  if (t < f.t0 || t > f.t1) return null;
  const span = f.t1 - f.t0;
  const p = span <= 0 ? 1 : (t - f.t0) / span;
  // A lost message dies where the wire is broken (the middle), not at the far end.
  return f.fate === "lost" ? p * 0.5 : p;
}

export type Mode = "ok" | "warn" | "fail" | "off" | "active";

export function bmsMode(s: string): Mode {
  return s.startsWith("FAULT") ? "warn" : s ? "ok" : "off";
}
export function hubMode(s: string): Mode {
  if (s.startsWith("RESTART") || s.startsWith("BOOT") || s.startsWith("OFF")) return "off";
  return /\bSTOP\b/.test(s) ? "warn" : "ok";
}
export function invMode(s: string): Mode {
  return s.startsWith("DISCHARG") ? "active" : "off";
}
export function invPowerW(s: string): number {
  const m = s.match(/(\d+)W\b/);
  return s.startsWith("DISCHARG") && m ? Number(m[1]) : 0;
}

/**
 * The invariant timer at t. While it runs: t − since. Once it clears (the inverter
 * stopped), hold the final window, since that number is the result.
 */
export function timerAt(tl: Timeline, t: number): { elapsed: number | null; stopped: boolean } {
  let since: number | null = null;
  let last: number | null = null;
  let now = 0;
  for (const f of tl.frames) {
    if (f.t > t) break;
    now = f.t;
    if (f.timerSince !== null) since = f.timerSince;
    else if (since !== null) {
      last = f.t - since;
      since = null;
    }
  }
  if (since !== null) return { elapsed: Math.max(0, now - since), stopped: false };
  return { elapsed: last, stopped: last !== null };
}
