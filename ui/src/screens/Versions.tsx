import { useEffect, useMemo, useState } from "react";
import type { Shared } from "../App";
import { Empty, ErrorState, Loading } from "../components/ui";
import { api } from "../lib/api";
import { href, useAsync, useFixtureFlag, useHeader } from "../lib/hooks";
import type { Counterexample, ReplayResult } from "../lib/types";
import { niceTicks, num, sutVersion } from "../lib/trace";

type Row = { sut: string; state: "loading" | "ok" | "error"; r?: ReplayResult; error?: string };

export default function VersionsScreen({ shared, cexId }: { shared: Shared; cexId: string | null }) {
  const cex = useAsync(() => api.cex(cexId as string), cexId);
  useFixtureFlag("cex", cex.data);
  useHeader(cexId ? `versions / ${cexId}` : "versions", `comparing ${(shared.describe?.sut_versions ?? []).length} versions`);
  if (!cexId) return <Empty>No counterexample to compare. Pick one from Checks.</Empty>;
  if (shared.describeError) return <ErrorState title="Could not load the SUT versions (describe)" error={shared.describeError} onRetry={shared.reload} />;
  if (cex.error) return <ErrorState title={`Could not load ${cexId}`} error={cex.error} onRetry={cex.reload} />;
  if (!cex.data || !shared.describe) return <Loading lines={5} />;
  return <VersionsView shared={shared} cex={cex.data} cexId={cexId} />;
}

function VersionsView({ shared, cex, cexId }: { shared: Shared; cex: Counterexample; cexId: string }) {
  const versions = useMemo(() => (shared.describe?.sut_versions ?? []).filter((v): v is string => typeof v === "string"), [shared.describe]);
  const [rows, setRows] = useState<Row[]>([]);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let live = true;
    setRows(versions.map((sut) => ({ sut, state: "loading" })));
    versions.forEach((sut, i) => {
      api.replay(cexId, sut).then(
        (r) => live && setRows((rs) => rs.map((x, j) => (j === i ? { sut, state: "ok", r } : x))),
        (e: Error) => live && setRows((rs) => rs.map((x, j) => (j === i ? { sut, state: "error", error: e.message } : x))),
      );
    });
    return () => {
      live = false;
    };
  }, [versions, cexId, nonce]);

  const anyFixture = rows.some((r) => r.r?._fixture === true);
  useFixtureFlag("versions", anyFixture ? { _fixture: true } : null);

  const inv = cex.invariant;
  const bound = num(inv?.bound_ms);
  const firstFault = cex.trace?.find((s) => inv?.timer_key && num(s.snapshot?.[inv.timer_key]) !== null);
  const faultAt = firstFault && inv?.timer_key ? num(firstFault.snapshot?.[inv.timer_key]) : null;
  const durations = rows.map((r) => num(r.r?.violation_window_ms?.duration_ms)).filter((d): d is number => d !== null);
  const scaleMax = Math.max(bound ?? 0, ...durations, 1) * 1.15;
  const ticks = niceTicks(scaleMax, 7);
  const axisMax = Math.max(scaleMax, ticks[ticks.length - 1]);
  const pct = (ms: number) => `${(Math.min(ms, axisMax) / axisMax) * 100}%`;
  const passing = rows.find((r) => r.r?.verdict === "PASS");

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <h1>Fix loop · {cexId}</h1>
          <span className="muted">
            The same counterexample replayed against every SUT version
            {faultAt !== null && ` · ${inv?.timer_key} starts at t = ${faultAt} ms`}
            {bound !== null && ` · budget ${bound} ms`}
          </span>
        </div>
        <div className="ph-actions">
          <button type="button" className="btn" onClick={() => setNonce((n) => n + 1)}>
            Re-run all
          </button>
          <a className="btn btn-primary" href={href("regress", cexId)}>
            Regression test →
          </a>
        </div>
      </div>

      {versions.length === 0 ? (
        <Empty>describe lists no sut_versions.</Empty>
      ) : (
        <section className="card" style={{ padding: "8px 20px", gap: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "230px minmax(0, 1fr) 170px", gap: 20, alignItems: "center", padding: "10px 0", borderBottom: "1px solid var(--line)", fontSize: 12, color: "var(--muted)" }}>
            <span>Version</span>
            <span>
              {inv?.id ?? "Invariant"} window: time the bounded condition held
              {bound !== null ? ` · dashed = ${bound} ms budget` : " · unbounded invariant, no budget"}
            </span>
            <span style={{ textAlign: "right" }}>{inv?.id ?? ""} on this replay</span>
          </div>
          {rows.map((row, i) => {
            const r = row.r;
            const w = r?.violation_window_ms ?? null;
            const invRes = r?.invariants?.find((x) => x?.id === inv?.id);
            const dur = num(w?.duration_ms);
            const over = dur !== null && bound !== null && dur > bound;
            const same = row.sut === cex.sut?.id;
            return (
              <div key={row.sut} style={{ display: "grid", gridTemplateColumns: "230px minmax(0, 1fr) 170px", gap: 20, alignItems: "center", padding: "16px 0", borderBottom: i === rows.length - 1 ? 0 : "1px solid var(--line)" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  <span className="mono" style={{ fontWeight: 600 }}>
                    {sutVersion(row.sut)}
                    {same && <span className="muted" style={{ fontWeight: 400 }}> · found on</span>}
                  </span>
                  <span className="small muted mono">
                    {r ? `${r.hash_match ? "trace identical" : `diverges at step ${r.first_divergence ?? "?"}`}${(r.skipped_moves ?? []).length ? ` · ${(r.skipped_moves ?? []).length} skipped` : ""}` : row.state === "loading" ? "replaying…" : ""}
                  </span>
                </div>
                <div style={{ position: "relative", height: 40 }}>
                  {row.state === "loading" && <div className="skel" style={{ position: "absolute", top: 13, left: 0, right: 0 }} />}
                  {row.state === "error" && (
                    <span className="mono small t-fail" style={{ position: "absolute", top: 12 }}>
                      {row.error}
                    </span>
                  )}
                  {r && (
                    <>
                      <div style={{ position: "absolute", top: 10, height: 20, left: 0, right: 0, borderRadius: 4, background: "#1A1F27" }} />
                      {dur !== null ? (
                        <>
                          <div style={{ position: "absolute", top: 10, height: 20, left: 0, width: pct(dur), borderRadius: 4, background: "var(--accent-bar)" }} />
                          {over && <div style={{ position: "absolute", top: 10, height: 20, left: pct(bound as number), width: `calc(${pct(dur)} - ${pct(bound as number)})`, background: "var(--fail)", opacity: 0.6 }} />}
                          {w?.open && <span className="mono small" style={{ position: "absolute", top: 12, left: `calc(${pct(dur)} + 6px)`, color: "var(--fail-text)" }}>still open at horizon</span>}
                        </>
                      ) : (
                        <span className="mono small muted" style={{ position: "absolute", top: 12, left: 10 }}>
                          condition never held
                        </span>
                      )}
                      {bound !== null && <div style={{ position: "absolute", top: 0, bottom: 0, left: pct(bound), borderLeft: "2px dashed var(--fail)" }} />}
                    </>
                  )}
                </div>
                <span className="mono" style={{ textAlign: "right", fontWeight: 600, color: invRes?.result === "PASS" ? "var(--pass)" : invRes?.result === "FAIL" ? "var(--fail-text)" : "var(--muted)" }}>
                  {r ? `${invRes?.result === "PASS" ? "✓" : invRes?.result === "FAIL" ? "✕" : ""} ${dur !== null ? `${w?.open ? "≥ " : ""}${dur} ms` : invRes?.result ?? "—"}` : row.state === "error" ? "error" : "…"}
                  {r && r.verdict !== invRes?.result && <span className="small muted" style={{ display: "block", fontWeight: 400 }}>run verdict {r.verdict}</span>}
                </span>
              </div>
            );
          })}
          <div style={{ display: "grid", gridTemplateColumns: "230px minmax(0, 1fr) 170px", gap: 20, padding: "4px 0 10px" }}>
            <span />
            <div style={{ position: "relative", height: 14 }} className="mono small faint">
              {ticks.map((t) => (
                <span key={t} style={{ position: "absolute", left: pct(t), transform: "translateX(-50%)" }}>
                  {t}
                </span>
              ))}
            </div>
            <span className="mono small faint" style={{ textAlign: "right" }}>ms</span>
          </div>
        </section>
      )}

      <div className="grid2">
        <section className="card">
          <b>What the replays show</b>
          {rows.every((r) => r.state !== "loading") ? (
            <ul style={{ margin: 0, paddingLeft: 18, color: "var(--text2)", lineHeight: 1.6 }}>
              {rows.map((row) => {
                const r = row.r;
                if (!r) return <li key={row.sut}>{sutVersion(row.sut)}: replay failed ({row.error}).</li>;
                const w = r.violation_window_ms;
                const fails = (r.invariants ?? []).filter((x) => x?.result === "FAIL").map((x) => x?.id);
                return (
                  <li key={row.sut}>
                    <span className="mono">{sutVersion(row.sut)}</span>:{" "}
                    {w ? `${w.invariant} window ${w.duration_ms} ms, ${(w.over_budget_ms ?? 0) > 0 ? `${w.over_budget_ms} ms over budget` : `${-(w.over_budget_ms ?? 0)} ms headroom`}` : "bounded condition never held"}
                    {fails.length ? `; fails ${fails.join(", ")}` : "; every invariant holds on this path"}.
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="skel" />
          )}
        </section>
        <section className="card">
          <b>Next step</b>
          <span style={{ color: "var(--text2)", lineHeight: 1.5 }}>
            {passing
              ? `${sutVersion(passing.sut)} passes this counterexample. A single replay only covers this one path, so re-run the full check against ${sutVersion(passing.sut)} to prove every invariant within bounds, then pin the path as a regression test.`
              : "No version passes this counterexample yet."}
          </span>
          {passing && (
            <code className="mono small" style={{ background: "var(--code)", border: "1px solid var(--line)", borderRadius: 8, padding: "8px 12px", color: "var(--text2)" }}>
              fleetflight check --sut {sutVersion(passing.sut)}
              <br />
              fleetflight regress --from {cexId}
            </code>
          )}
        </section>
      </div>
    </>
  );
}
