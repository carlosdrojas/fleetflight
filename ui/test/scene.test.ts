import { describe, expect, it } from "vitest";
import { buildTimeline, flightProgress, frameAt, timerAt } from "../src/lib/scene";
import type { ReplayResult, TraceStep } from "../src/lib/types";

// Trimmed from a real replay of cex-286e0592 (bms_fault@0 + network_loss@0).
const snap = (t: number, bms: string, hub: string, inv: string, link: string, since: number | null) => ({
  t_ms: t, bms, hub, inv, link, i1_since_ms: since,
});
const DIS = "DISCHARGING 5000W seq41 e1";
const STOP = "ONLINE e1 seq42 STOP";
const ev = (t: number, name: string, detail: string) => ({ t_ms: t, name, detail });

function replay(stopAt: number, stopMode: string, horizon = 4000): ReplayResult {
  const steps: TraceStep[] = [
    { step: 0, t_ms: 0, snapshot: snap(0, "HEALTHY", "ONLINE e1 seq41 DISCHARGE 5000W", DIS, "UP", null), events: [] },
    { step: 1, t_ms: 0, snapshot: snap(0, "FAULTED unacked", "ONLINE e1 seq41 DISCHARGE 5000W", DIS, "UP", 0), events: [ev(0, "bms_fault", "bms_fault"), ev(0, "send", "fault@0 FAULT bms→hub")] },
    { step: 2, t_ms: 0, snapshot: snap(0, "FAULTED unacked", "ONLINE e1 seq41 DISCHARGE 5000W", DIS, "DOWN", 0), events: [ev(0, "network_loss", "network_loss")] },
    { step: 3, t_ms: 50, snapshot: snap(50, "FAULTED unacked", STOP, DIS, "DOWN", 0), events: [ev(50, "deliver", "fault@0 → hub"), ev(50, "lost", "cmd@50 CMD hub→inv seq42 STOP 0W e1 (link down)"), ev(50, "send", "ack@50 ACK hub→bms")] },
    { step: 4, t_ms: 100, snapshot: snap(100, "FAULTED acked", STOP, DIS, "DOWN", 0), events: [ev(100, "deliver", "ack@50 → bms"), ev(100, "lost", "cmd@100 CMD hub→inv seq42 STOP 0W e1 (link down)")] },
  ];
  for (let t = 150; t <= stopAt + 100; t += 50) {
    const stopped = t >= stopAt;
    steps.push({
      step: steps.length,
      t_ms: t,
      snapshot: snap(t, "FAULTED acked", STOP, stopped ? `${stopMode} seq41 e1` : DIS, "DOWN", stopped ? null : 0),
      events: t === stopAt ? [ev(t, "inv_mode", `inverter DISCHARGING → ${stopMode}`)] : [],
      violations: !stopped && t >= 500 ? ["I1"] : [],
    });
  }
  return { steps, horizon_ms: horizon, violation_window_ms: { start_ms: 0, end_ms: stopAt, duration_ms: stopAt } };
}

describe("buildTimeline", () => {
  const v031 = buildTimeline(replay(1050, "IDLE"), "i1_since_ms");
  const v033 = buildTimeline(replay(250, "SHUTDOWN"), "i1_since_ms");

  it("pairs sends with deliveries and marks dropped commands as lost", () => {
    const fault = v031.flights.find((f) => f.id === "fault@0");
    expect(fault).toMatchObject({ kind: "FAULT", from: "bms", to: "hub", t0: 0, t1: 50, fate: "deliver" });
    const stop = v031.flights.find((f) => f.id === "cmd@50");
    expect(stop).toMatchObject({ label: "STOP", from: "hub", to: "inv", fate: "lost", t0: 50 });
    expect(v031.flights.find((f) => f.id === "ack@50")).toMatchObject({ to: "bms", t1: 100, fate: "deliver" });
  });

  it("finds the first violation and ends the playback shortly after the window closes", () => {
    expect(v031.violationAt).toBe(500);
    expect(v031.violated).toEqual(["I1"]);
    expect(v033.violationAt).toBeNull();
    expect(v031.endMs).toBeGreaterThan(1050);
    expect(v031.endMs).toBeLessThan(4000);
  });

  it("captions one lost STOP, not every retry", () => {
    expect(v031.captions.filter((c) => c.text.startsWith("STOP to inverter lost"))).toHaveLength(1);
  });

  it("frameAt returns the last step at or before t", () => {
    expect(frameAt(v031, 0)?.link).toBe("DOWN");
    expect(frameAt(v031, 74)?.t).toBe(50);
  });

  it("timerAt runs while discharging, then holds the final window", () => {
    expect(timerAt(v031, 600)).toEqual({ elapsed: 600, stopped: false });
    expect(timerAt(v033, 200)).toEqual({ elapsed: 200, stopped: false });
    expect(timerAt(v033, 900)).toEqual({ elapsed: 250, stopped: true });
    expect(timerAt(v031, 1100)).toEqual({ elapsed: 1050, stopped: true });
  });

  it("lost packets stop at the break in the wire", () => {
    const stop = v031.flights.find((f) => f.id === "cmd@50")!;
    expect(flightProgress(stop, stop.t1)).toBe(0.5);
    expect(flightProgress(stop, stop.t1 + 1)).toBeNull();
  });
});
