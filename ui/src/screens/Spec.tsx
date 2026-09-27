import type { Shared } from "../App";
import { AssumptionRow, Empty, ErrorState, Loading } from "../components/ui";
import { href, useHeader } from "../lib/hooks";
import type { Component, Injectable } from "../lib/types";
import { fmtDuration, num, shortHash, sutVersion } from "../lib/trace";

export default function SpecScreen({ shared }: { shared: Shared }) {
  useHeader("spec");
  const d = shared.describe;
  if (shared.describeError) return <ErrorState title="Could not load the model description" error={shared.describeError} onRetry={shared.reload} />;
  if (!d) return <Loading lines={6} />;

  const comps = (d.components ?? []).filter(Boolean);
  const invs = (d.invariants ?? []).filter(Boolean);
  const inj = (d.injectables ?? []).filter(Boolean);
  const assumptions = (d.assumptions ?? []).filter((a) => typeof a === "string");
  const b = d.bounds ?? {};
  const tick = num(d.tick_ms);
  const constants = Object.entries(d.constants ?? {});

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <h1>Spec · {d.model?.name ?? "unnamed model"}</h1>
          <span className="muted">
            model {d.model?.version ?? "—"} · <span className="mono">{shortHash(d.model?.hash)}</span> · checked against{" "}
            {(d.sut_versions ?? []).length || "no"} SUT version{(d.sut_versions ?? []).length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="ph-actions">
          <a className="btn btn-primary" href={href("checks")}>
            View checks →
          </a>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.1fr) minmax(0, 1fr)", gap: 20, alignItems: "start" }}>
        <section className="card">
          <div className="card-h">
            <b>System model</b>
            <span className="sub">
              {comps.length} component{comps.length === 1 ? "" : "s"}
              {tick !== null && ` · ${tick} ms ticks`}
            </span>
          </div>
          {comps.length ? <SystemDiagram comps={comps} /> : <Empty>describe has no components.</Empty>}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span className="small muted">
              Injectable faults the checker may combine
              {num(b.max_injections) !== null && ` (≤ ${b.max_injections} per trace)`}
            </span>
            {inj.length ? (
              <div className="chips">
                {inj.map((x, i) => (
                  <span key={`${x.name}-${i}`} title={x.description}>
                    {injLabel(x)}
                  </span>
                ))}
              </div>
            ) : (
              <span className="small muted">none declared</span>
            )}
          </div>
        </section>

        <section className="card" style={{ gap: 10 }}>
          <div className="card-h">
            <b>Invariants</b>
            <span className="sub">{invs.length} properties · checked on every state</span>
          </div>
          {invs.length === 0 && <Empty>describe has no invariants.</Empty>}
          {invs.map((v, i) => (
            <div key={v.id ?? i} style={{ border: "1px solid var(--line)", borderRadius: 8, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 4 }} title={v.description}>
              <div className="mono" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                <b>{v.id ?? "?"}</b>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.name}</span>
                {num(v.bound_ms) !== null && (
                  <span className="t-accent" style={{ marginLeft: "auto", fontSize: 11, whiteSpace: "nowrap" }}>
                    bounded {fmtDuration(v.bound_ms as number)}
                  </span>
                )}
              </div>
              <div className="mono muted" style={{ fontSize: 12 }}>{v.formula || v.description || "—"}</div>
            </div>
          ))}
        </section>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", gap: 20 }}>
        <section className="card" style={{ gap: 8 }}>
          <div className="card-h">
            <b>Assumptions</b>
            <span className="sub">· printed on every report</span>
          </div>
          {assumptions.length ? assumptions.map((a, i) => <AssumptionRow key={i} text={a} />) : <span className="muted">none declared</span>}
        </section>
        <section className="card" style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "12px 20px", alignContent: "start" }}>
          <div style={{ gridColumn: "span 2", fontWeight: 600 }}>Search bounds</div>
          <Field k="Strategy" v="BFS · shortest counterexample first" />
          <Field k="Horizon" v={num(b.horizon_ms) !== null ? `${fmtDuration(b.horizon_ms as number)}${tick ? ` · ${Math.round((b.horizon_ms as number) / tick)} ticks` : ""}` : "—"} />
          <Field k="Max depth" v={num(b.max_depth) !== null ? `${b.max_depth} moves` : "—"} />
          <Field k="Injections per trace" v={num(b.max_injections) !== null ? `≤ ${b.max_injections}` : "—"} />
          {constants.length > 0 && (
            <div style={{ gridColumn: "span 2", display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="small muted">Constants</span>
              <div className="chips">
                {constants.map(([k, v]) => (
                  <span key={k}>
                    {k}={String(v)}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div style={{ gridColumn: "span 2", display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="small muted">SUT versions</span>
            <div className="chips">
              {(d.sut_versions ?? []).map((s) => (
                <span key={s} style={s === d.sut?.id ? { color: "var(--accent)" } : undefined}>
                  {sutVersion(s)}
                </span>
              ))}
              {!(d.sut_versions ?? []).length && <span>none</span>}
            </div>
          </div>
        </section>
      </div>
    </>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span className="small muted">{k}</span>
      <span className="mono">{v}</span>
    </div>
  );
}

function injLabel(x: Injectable): string {
  const params = (x.params ?? [])
    .map((p) => {
      if (Array.isArray(p.values) && p.values.length && p.values.every((v) => typeof v === "number")) {
        const vs = p.values as number[];
        return `${p.name} ≤ ${Math.max(...vs)}`;
      }
      return null;
    })
    .filter(Boolean);
  return [x.name ?? "?", ...params].join(" ");
}

/** Components left→right joined by dashed links; each lists its states. SUT-owned ones are tagged. */
function SystemDiagram({ comps }: { comps: Component[] }) {
  return (
    <div role="list" aria-label="System model components" style={{ display: "flex", alignItems: "stretch" }}>
      {comps.map((c, i) => {
        const sut = c.owner === "sut";
        return (
          <div key={c.id ?? i} style={{ display: "flex", alignItems: "center", flex: "1 1 0", minWidth: 0 }}>
            <div role="listitem" title={c.description} style={{ flex: "1 1 0", minWidth: 0, alignSelf: "stretch", background: "var(--nav)", border: `1px solid ${sut ? "var(--warn-line)" : "var(--line2)"}`, borderRadius: 10, padding: "12px 12px 10px", display: "flex", flexDirection: "column", gap: 6 }}>
              <span style={{ fontWeight: 600, fontSize: 14, fontFamily: "var(--mono)" }}>{c.name ?? c.id ?? "?"}</span>
              <div className="mono" style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11.5, color: "#9AA3B1", flexGrow: 1 }}>
                {(c.states ?? []).map((st, j) => (
                  <span key={j} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={st}>
                    {st}
                  </span>
                ))}
              </div>
              <span className="mono" style={{ fontSize: 10.5, color: sut ? "var(--warn)" : "var(--muted)", marginTop: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {sut ? "under test" : c.owner === "model" ? "environment" : c.owner ?? ""}
              </span>
            </div>
            {i < comps.length - 1 && <span aria-hidden="true" style={{ width: 22, flexShrink: 0, borderTop: "1.5px dashed var(--accent)" }} />}
          </div>
        );
      })}
    </div>
  );
}
