import type { Shared } from "../App";
import { Empty, ErrorState, Loading, Result } from "../components/ui";
import { api } from "../lib/api";
import { href, useAsync, useFixtureFlag, useHeader } from "../lib/hooks";
import type { CheckReport, RunRow } from "../lib/types";
import { fmtCompact, fmtInt, fmtMs, fmtSec, num, sutVersion } from "../lib/trace";

export default function ChecksScreen({ shared, runId }: { shared: Shared; runId: string | null }) {
  const rows = (shared.runs?.runs ?? []).filter((r): r is RunRow => !!r && typeof r.run_id === "string");
  const selected = runId ?? rows[0]?.run_id ?? null;
  const report = useAsync(() => api.run(selected as string), selected);
  useFixtureFlag("report", report.data);
  useHeader(selected ? `checks / ${selected}` : "checks", report.data?.sut?.id ?? null);

  return (
    <>
      <section aria-label="Runs" style={{ display: "flex", gap: 10, alignItems: "stretch", overflowX: "auto", flexShrink: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", paddingRight: 6, flexShrink: 0 }}>
          <b>Runs</b>
          <span className="small muted">{rows.length} run{rows.length === 1 ? "" : "s"}</span>
        </div>
        {shared.runsError && <ErrorState title="Could not load runs" error={shared.runsError} onRetry={shared.reload} />}
        {!shared.runs && !shared.runsError && <div className="skel" style={{ width: 200, alignSelf: "center" }} />}
        {shared.runs && rows.length === 0 && (
          <span className="small muted" style={{ alignSelf: "center" }}>
            No check reports yet. Run <span className="mono">fleetflight check</span>.
          </span>
        )}
        {rows.map((r) => (
          <a
            key={r.run_id}
            href={href("checks", r.run_id)}
            aria-current={r.run_id === selected ? "page" : undefined}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 2,
              padding: "8px 14px",
              borderRadius: 10,
              textDecoration: "none",
              color: "var(--text)",
              flexShrink: 0,
              minWidth: 220,
              background: r.run_id === selected ? "var(--raise)" : "var(--panel)",
              border: `1px solid ${r.run_id === selected ? "#3a4658" : "var(--line)"}`,
            }}
          >
            <span style={{ display: "flex", gap: 12, alignItems: "center" }}>
              <span className="mono" style={{ fontSize: 13 }}>{r.run_id}</span>
              <span style={{ marginLeft: "auto", fontSize: 12 }}>
                <Result r={r.verdict} />
              </span>
            </span>
            <span className="small muted mono">
              {sutVersion(r.sut)} · {fmtCompact(r.states)} states{fmtSec(r.wall_s) ? ` · ${fmtSec(r.wall_s)}` : ""}
            </span>
          </a>
        ))}
      </section>

      {!selected && shared.runs && rows.length > 0 && <Empty>Pick a run above.</Empty>}
      {report.error && <ErrorState title={`Could not load run ${selected}`} error={report.error} onRetry={report.reload} />}
      {report.loading && !report.data && <Loading lines={5} />}
      {report.data && <RunDetail r={report.data} />}
    </>
  );
}

function RunDetail({ r }: { r: CheckReport }) {
  const invs = (r.invariants ?? []).filter(Boolean);
  const failed = invs.filter((i) => i.result === "FAIL");
  const s = r.stats ?? {};
  const depthsRaw = Array.isArray(s.new_states_per_depth) ? s.new_states_per_depth : [];
  const depths = depthsRaw.map((v) => num(v) ?? 0);
  const cexDepths = new Map<number, string[]>();
  for (const f of failed) {
    const d = num(f.depth);
    if (d !== null && f.counterexample) cexDepths.set(d, [...(cexDepths.get(d) ?? []), f.counterexample]);
  }
  const shortest = failed.map((f) => num(f.depth)).filter((d): d is number => d !== null);
  const firstCex = failed.find((f) => f.counterexample)?.counterexample;
  const max = Math.max(1, ...depths);
  const labelEvery = Math.max(1, Math.ceil(depths.length / 10));
  const cols = "50px minmax(0, 1.3fr) minmax(0, 1.8fr) 90px 210px";

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <div className="ph-title">
            <h1>Check {r.run_id ?? ""}</h1>
            {invs.length > 0 &&
              (failed.length ? (
                <span className="chip-fail">
                  {failed.length} of {invs.length} violated
                </span>
              ) : (
                <span className="chip-pass">all {invs.length} hold</span>
              ))}
          </div>
          <span className="muted">
            {r.sut?.id ?? "unknown SUT"} · {fmtSec(s.wall_s) ? `finished in ${fmtSec(s.wall_s)}` : "duration unknown"} ·{" "}
            {s.complete === true ? "every reachable state within bounds" : s.complete === false ? <span className="t-warn">search stopped early: bounds not exhausted</span> : "completeness unknown"}
          </span>
        </div>
        <div className="ph-actions">
          {firstCex && (
            <a className="btn btn-primary" href={href("cex", firstCex)}>
              Open {firstCex} →
            </a>
          )}
        </div>
      </div>

      <div className="tiles">
        <Tile label="States explored" value={fmtInt(s.states)} />
        <Tile label="Transitions" value={fmtCompact(s.transitions)} />
        <Tile label="Max depth reached" value={fmtInt(s.max_depth_reached)} unit="moves" />
        <Tile
          label="Shortest violation"
          value={shortest.length ? String(Math.min(...shortest)) : "none"}
          unit={shortest.length ? "moves" : undefined}
          tone={shortest.length ? "t-fail" : "t-pass"}
        />
      </div>

      <section className="card">
        <div className="card-h">
          <b>New states per depth</b>
          <span className="sub">
            BFS frontier{cexDepths.size ? " · red = depth where a counterexample was found" : ""}
            {num(r.bounds?.max_depth) !== null && ` · bound ${r.bounds?.max_depth}`}
          </span>
        </div>
        {depths.length === 0 ? (
          <span className="muted small">The report has no per-depth stats.</span>
        ) : (
          <>
            <div role="img" aria-label={`New states per depth, ${depths.length} depths, peak ${fmtInt(max)}`} style={{ display: "flex", alignItems: "flex-end", gap: depths.length > 60 ? 1 : 4, height: 130, borderBottom: "1px solid var(--line2)" }}>
              {depths.map((v, d) => (
                <div
                  key={d}
                  title={`depth ${d}: ${fmtInt(v)} new states${cexDepths.has(d) ? ` · ${cexDepths.get(d)!.join(", ")}` : ""}`}
                  style={{ flex: "1 1 0", height: `${Math.max(v > 0 ? 2 : 0, (v / max) * 126)}px`, background: cexDepths.has(d) ? "var(--fail)" : "var(--accent-bar)", borderRadius: "3px 3px 0 0" }}
                />
              ))}
            </div>
            <div className="mono faint" style={{ display: "flex", fontSize: 11 }}>
              {depths.map((_, d) => (
                <span key={d} style={{ flex: "1 1 0", minWidth: 0, overflow: "visible", whiteSpace: "nowrap", color: cexDepths.has(d) ? "var(--fail-text)" : undefined }}>
                  {cexDepths.has(d) ? `▲ ${d}` : d % labelEvery === 0 ? d : ""}
                </span>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="tbl">
        <div className="tbl-row tbl-head" style={{ gridTemplateColumns: cols }}>
          <span>ID</span>
          <span>Invariant</span>
          <span>Property</span>
          <span>Result</span>
          <span>Evidence</span>
        </div>
        {invs.length === 0 && <div className="tbl-row muted">The report lists no invariants.</div>}
        {invs.map((v, i) => (
          <div key={v.id ?? i} className={`tbl-row${v.result === "FAIL" ? " fail" : ""}`} style={{ gridTemplateColumns: cols }}>
            <b className="mono">{v.id}</b>
            <span className="mono" style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis" }} title={v.formula}>
              {v.name}
            </span>
            <span style={{ color: "var(--text2)" }}>{v.description}</span>
            <Result r={v.result} />
            {v.result === "FAIL" && v.counterexample ? (
              <a className="mono" style={{ fontSize: 13, fontWeight: 500 }} href={href("cex", v.counterexample)}>
                {v.counterexample}
                {num(v.depth) !== null && ` · ${v.depth} moves`} →
              </a>
            ) : v.result === "PASS" ? (
              <span className="muted" style={{ fontSize: 13 }}>
                {num(v.worst_case_ms) !== null ? `worst case ${fmtMs(v.worst_case_ms)}` : "holds in all states"}
              </span>
            ) : (
              <span className="muted">—</span>
            )}
          </div>
        ))}
      </section>
      {(r.notes ?? []).length > 0 && (
        <div className="small muted">
          {(r.notes ?? []).map((n, i) => (
            <div key={i}>{n}</div>
          ))}
        </div>
      )}
    </>
  );
}

function Tile({ label, value, unit, tone }: { label: string; value: string; unit?: string; tone?: string }) {
  return (
    <div className="tile">
      <div className="tile-l">{label}</div>
      <div className={`tile-v ${tone ?? ""}`}>
        {value} {unit && <small>{unit}</small>}
      </div>
    </div>
  );
}
