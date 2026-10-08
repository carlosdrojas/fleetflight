import type { Shared } from "../App";
import { Empty, ErrorState, Loading } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { href, useAsync, useFixtureFlag, useHeader } from "../lib/hooks";
import type { Counterexample } from "../lib/types";
import { shortHash, sutVersion } from "../lib/trace";

// `GET /api/regress` and `GET /api/regress/<cex>` are a CONTRACT REQUEST (status/04-ui.md).
// Until `serve` has them, this screen shows what a regression test is built from: the
// counterexample's injected moves, tick count and expected hash, straight from /api/cex.

export default function RegressScreen({ shared, cexId }: { shared: Shared; cexId: string | null }) {
  const selected = cexId ?? shared.cexIds[0] ?? null;
  const list = useAsync(() => api.regressList().catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))), "regress");
  const source = useAsync(() => api.regressSource(selected as string).catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))), selected);
  const cex = useAsync(() => api.cex(selected as string), selected);
  useFixtureFlag("regress", list.data);
  useFixtureFlag("regress-src", source.data);
  useFixtureFlag("cex", cex.data);
  useHeader(selected ? `regressions / ${selected}` : "regressions", cex.data?.sut?.id ?? null);

  const apiMissing = !list.loading && !list.error && list.data === null;
  const tests = (list.data?.tests ?? []).filter(Boolean);
  const candidates = [...new Set([...tests.map((t) => t.cex).filter((c): c is string => !!c), ...shared.cexIds])];

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <h1>Regressions{selected ? ` · ${selected}` : ""}</h1>
          <span className="muted">Every counterexample becomes a permanent test: its injected moves, replayed through the same transition code on every commit.</span>
        </div>
      </div>

      {apiMissing && (
        <div className="banner warn" style={{ gap: 10 }}>
          <b className="t-warn">No /api/regress endpoint on this server.</b>
          <span className="small" style={{ color: "var(--text2)" }}>
            Showing the regression <i>inputs</i> from the counterexample. The test file itself is written by <span className="mono">fleetflight regress</span>.
          </span>
        </div>
      )}
      {list.error && <ErrorState title="Could not load regression tests" error={list.error} onRetry={list.reload} />}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)", gap: 18 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
          {!selected && <Empty>No counterexamples yet, so no regression tests to generate.</Empty>}
          {selected && source.data?.source ? (
            <section className="card card-code" style={{ padding: 0, gap: 0, overflow: "hidden" }}>
              <div className="mono" style={{ display: "flex", padding: "12px 16px", borderBottom: "1px solid var(--line)", fontSize: 12 }}>
                <span>{source.data.path ?? `test_${selected}.py`}</span>
              </div>
              <CodeBlock text={source.data.source} />
            </section>
          ) : (
            selected && (
              <>
                {cex.error && <ErrorState title={`Could not load ${selected}`} error={cex.error} onRetry={cex.reload} />}
                {!cex.data && !cex.error && <Loading lines={4} />}
                {cex.data && <Inputs cex={cex.data} />}
              </>
            )
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 0 }}>
          <section className="card" style={{ padding: "14px 20px", gap: 0 }}>
            <div className="card-h" style={{ paddingBottom: 8 }}>
              <b>Suite</b>
              <span className="sub">{apiMissing || !list.data ? `${candidates.length} counterexample${candidates.length === 1 ? "" : "s"} in out/` : `${tests.length} test${tests.length === 1 ? "" : "s"} in tests/regress`}</span>
            </div>
            {candidates.length === 0 && <span className="small muted">Nothing yet.</span>}
            {candidates.map((c) => {
              const t = tests.find((x) => x.cex === c);
              return (
                <a key={c} href={href("regress", c)} aria-current={c === selected ? "page" : undefined} style={{ display: "grid", gridTemplateColumns: "110px 50px minmax(0, 1fr)", gap: 12, padding: "8px 6px", borderTop: "1px solid var(--line)", fontSize: 13, textDecoration: "none", color: "var(--text)", background: c === selected ? "#151E2C" : undefined }}>
                  <span className="mono t-accent">{c}</span>
                  <span className="mono">{t?.invariant ?? (c === selected ? cex.data?.invariant?.id : "") ?? ""}</span>
                  <span className="mono small muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t?.path ?? (list.data ? "not generated yet" : "")}
                  </span>
                </a>
              );
            })}
          </section>
          {selected && (
            <section className="card card-code">
              <div className="code">
                <div>
                  <span className="p">$</span> fleetflight regress --from {selected}
                </div>
                <div>
                  <span className="p">$</span> pytest tests/regress -q
                </div>
                <div className="p" style={{ marginTop: 6 }}># commands to run locally; this page does not execute them</div>
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  );
}

function Inputs({ cex }: { cex: Counterexample }) {
  const moves = (cex.moves ?? []).filter(Boolean);
  return (
    <section className="card">
      <div className="card-h">
        <b>What the test replays</b>
        <span className="sub">from {cex.id}.json · found on {sutVersion(cex.sut?.id)}</span>
      </div>
      <div className="tbl" style={{ background: "var(--code)" }}>
        <div className="tbl-row tbl-head" style={{ gridTemplateColumns: "90px 90px minmax(0, 1fr)" }}>
          <span>tick_index</span>
          <span>t_ms</span>
          <span>injected move</span>
        </div>
        {moves.length === 0 && <div className="tbl-row muted">No injected moves: the path is ticks only.</div>}
        {moves.map((m, i) => (
          <div key={i} className="tbl-row mono" style={{ gridTemplateColumns: "90px 90px minmax(0, 1fr)", fontSize: 13 }}>
            <span className="muted">{m.tick_index ?? "?"}</span>
            <span className="muted">{m.t_ms ?? "?"}</span>
            <span className="t-warn">{m.move?.label ?? m.move?.name ?? "?"}</span>
          </div>
        ))}
      </div>
      <div className="kv" style={{ gridTemplateColumns: "170px minmax(0, 1fr)" }}>
        <span className="k">ticks</span>
        <span>{cex.ticks ?? "—"}</span>
        <span className="k">asserts invariant</span>
        <span>
          {cex.invariant?.id} {cex.invariant?.name}
        </span>
        <span className="k">formula</span>
        <span>{cex.invariant?.formula ?? "—"}</span>
        <span className="k">expected hash</span>
        <span>{shortHash(cex.trace_hash)}</span>
      </div>
      <span className="small muted">
        The test fails while the SUT still reproduces the violation and passes once {cex.invariant?.id ?? "the invariant"} holds on this path. The rest of the path follows from the model.
      </span>
    </section>
  );
}

function CodeBlock({ text }: { text: string }) {
  const lines = text.replace(/\n$/, "").split("\n");
  return (
    <div style={{ display: "flex", padding: "12px 0", maxHeight: 520, overflow: "auto" }}>
      <div className="mono" style={{ width: 48, flexShrink: 0, textAlign: "right", paddingRight: 14, color: "var(--faint)", fontSize: 13, lineHeight: 1.75 }}>
        {lines.map((_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <div className="mono" style={{ whiteSpace: "pre", color: "var(--text2)", fontSize: 13, lineHeight: 1.75 }}>
        {lines.map((l, i) => (
          <div key={i} style={{ color: /^\s*#/.test(l) ? "var(--faint)" : undefined }}>
            {l || " "}
          </div>
        ))}
      </div>
    </div>
  );
}
