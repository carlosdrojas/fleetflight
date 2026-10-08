// Never-crash checks: components must render partial or malformed payloads.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Swimlane from "../src/components/Swimlane";
import { StatePanel, TraceList } from "../src/components/TracePanels";
import type { Counterexample, TraceStep } from "../src/lib/types";

const cex: Counterexample = JSON.parse(readFileSync(resolve(import.meta.dirname, "../../fixtures/cex-0017.json"), "utf8"));
const lanes = [
  { key: "bms", label: "BMS" },
  { key: "inv", label: "Inverter" },
];
const noop = () => {};

const weird: TraceStep[][] = [
  [{}],
  [{ step: 0 }, { move: null, snapshot: undefined }, { t_ms: 50, move: { injected: true } }],
  [{ t_ms: 0, snapshot: { t_ms: 0, bms: null, inv: 7 } }, { t_ms: 0, snapshot: { t_ms: 0 }, events: [{}], violations: ["I1"] }],
];

describe("Swimlane", () => {
  it("renders the fixture counterexample with a deadline and hatch", () => {
    const html = renderToString(<Swimlane trace={cex.trace!} lanes={lanes} cursor={16} onPick={noop} invariant={cex.invariant} violatedAtMs={cex.violated_at_ms} />);
    expect(html).toContain("deadline");
    expect(html).toContain("ff-hatch");
    expect(html).toContain("FAULTED");
  });
  it.each(weird)("does not crash on malformed trace %#", (...trace) => {
    const t = trace as unknown as TraceStep[];
    expect(() => renderToString(<Swimlane trace={t} lanes={lanes} cursor={99} onPick={noop} invariant={{ timer_key: "x", bound_ms: 10 }} violatedAtMs={null} />)).not.toThrow();
  });
});

describe("Trace panels", () => {
  it.each(weird)("TraceList and StatePanel survive malformed trace %#", (...trace) => {
    const t = trace as unknown as TraceStep[];
    expect(() => renderToString(<TraceList trace={t} laneKeys={["bms"]} cursor={0} onPick={noop} />)).not.toThrow();
    expect(() => renderToString(<StatePanel trace={t} index={t.length - 1} keys={lanes} />)).not.toThrow();
  });
  it("StatePanel renders nothing for an out-of-range index", () => {
    expect(renderToString(<StatePanel trace={[]} index={3} keys={lanes} />)).toBe("");
  });
});
