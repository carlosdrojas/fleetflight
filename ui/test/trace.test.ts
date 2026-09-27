import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { collapseTrace, laneDefs, moveLane, niceTicks, segments, stateKeys, timerWindows, tone } from "../src/lib/trace";
import type { Counterexample, Describe, TraceStep } from "../src/lib/types";

const fx = (f: string) => JSON.parse(readFileSync(resolve(import.meta.dirname, "../../fixtures", f), "utf8"));
const cex: Counterexample = fx("cex-0017.json");
const desc: Describe = fx("describe.json");
const trace = cex.trace as TraceStep[];

const snap = (t: number, v: Record<string, string | number | null>): TraceStep => ({ t_ms: t, snapshot: { t_ms: t, ...v } });

describe("laneDefs", () => {
  it("uses snapshot_keys with lane=true, in describe order", () => {
    expect(laneDefs(desc, trace).map((l) => l.key)).toEqual(["bms", "bus", "hub", "inv"]);
  });
  it("falls back to string-valued snapshot keys without describe", () => {
    const keys = laneDefs(null, [snap(0, { a: "X", n: 3, b: "" })]).map((l) => l.key);
    expect(keys).toEqual(["a", "b"]);
  });
  it("survives an empty trace and missing describe", () => {
    expect(laneDefs(undefined, [])).toEqual([]);
  });
});

describe("stateKeys", () => {
  it("lists describe keys first, then any extra snapshot keys", () => {
    const keys = stateKeys(desc, [snap(0, { bms: "X", extra: 1 })]).map((k) => k.key);
    expect(keys.slice(0, 4)).toEqual(["bms", "bus", "hub", "inv"]);
    expect(keys.at(-1)).toBe("extra");
    expect(keys).not.toContain("t_ms");
  });
});

describe("segments", () => {
  it("groups consecutive equal values and ends each where the next begins", () => {
    const segs = segments(trace, "hub");
    expect(segs.map((s) => [s.value, s.start_ms, s.end_ms])).toEqual([
      ["ONLINE", 0, 200],
      ["RESTARTING", 200, 600],
      ["ONLINE", 600, 650],
    ]);
    expect(segs[1].firstStep).toBe(7);
  });
  it("keeps zero-width states from same-time injections", () => {
    const segs = segments(trace, "bus");
    expect(segs.some((s) => s.start_ms === 100 && s.end_ms === 100)).toBe(true);
  });
  it("treats null and missing as empty", () => {
    const segs = segments([snap(0, { k: null }), snap(50, {}), snap(100, { k: "A" })], "k");
    expect(segs.map((s) => s.value)).toEqual(["", "A"]);
  });
});

describe("timerWindows", () => {
  it("finds the I1 window in the counterexample, open at the end", () => {
    expect(timerWindows(trace, "i1_since_ms")).toEqual([{ start_ms: 100, end_ms: 650, open: true, firstStep: 3, lastStep: 16 }]);
  });
  it("closes a window when the timer becomes null", () => {
    const w = timerWindows([snap(0, { t: null }), snap(50, { t: 50 }), snap(100, { t: 50 }), snap(150, { t: null })], "t");
    expect(w).toEqual([{ start_ms: 50, end_ms: 150, open: false, firstStep: 1, lastStep: 2 }]);
  });
  it("returns nothing when the timer never starts", () => {
    expect(timerWindows(trace, "i5_since_ms")).toEqual([]);
  });
});

describe("collapseTrace", () => {
  it("keeps init, injections, events, lane changes and the last step; folds idle ticks", () => {
    const rows = collapseTrace(trace, ["bms", "bus", "hub", "inv"]);
    const steps = rows.filter((r) => r.kind === "step").map((r) => (r as { index: number }).index);
    expect(steps).toEqual([0, 3, 4, 7, 15, 16]);
    const hidden = rows.reduce((n, r) => n + (r.kind === "gap" ? r.count : 0), 0);
    expect(hidden + steps.length).toBe(trace.length);
  });
  it("keeps the cursor step visible", () => {
    const rows = collapseTrace(trace, ["bms", "bus", "hub", "inv"], 10);
    expect(rows.some((r) => r.kind === "step" && r.index === 10)).toBe(true);
  });
});

describe("misc", () => {
  it("tone colours by first word, unknown words stay neutral-accent", () => {
    expect(tone("FAULTED")).toBe("fail");
    expect(tone("DISCHARGING 5000W seq41")).toBe("accent");
    expect(tone("RESTARTING")).toBe("warn");
    expect(tone("")).toBe("empty");
  });
  it("moveLane maps by prefix and returns null otherwise", () => {
    const lanes = laneDefs(desc, trace);
    expect(moveLane("bus_delay", lanes)).toBe("bus");
    expect(moveLane("hub_restart", lanes)).toBe("hub");
    expect(moveLane("network_loss", lanes)).toBeNull();
  });
  it("niceTicks stays within the tick budget", () => {
    expect(niceTicks(650, 12)).toEqual([0, 100, 200, 300, 400, 500, 600]);
    expect(niceTicks(0).length).toBeGreaterThan(0);
  });
});
