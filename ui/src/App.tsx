import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, SITE_MODE } from "./lib/api";
import { FixtureCtx, HeaderCtx, href, useAsync, useFixtureFlag, useRoute } from "./lib/hooks";
import type { Describe, RunList } from "./lib/types";
import { sutVersion } from "./lib/trace";
import SpecScreen from "./screens/Spec";
import ChecksScreen from "./screens/Checks";
import CexScreen from "./screens/Cex";
import ReplayScreen from "./screens/Replay";
import VersionsScreen from "./screens/Versions";
import RegressScreen from "./screens/Regress";
import { Loading } from "./components/ui";

// three.js is ~0.5 MB; only load it when the 3D screen opens.
const SceneScreen = lazy(() => import("./screens/Scene"));
const REPO_URL = import.meta.env.VITE_REPO_URL as string | undefined;

export interface Shared {
  describe: Describe | null;
  describeError: string | null;
  runs: RunList | null;
  runsError: string | null;
  /** Counterexample ids across all runs, newest run first, de-duplicated. */
  cexIds: string[];
  reload: () => void;
}

const I = {
  spec: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="m10 13-2 2 2 2" />
      <path d="m14 13 2 2-2 2" />
    </>
  ),
  checks: (
    <>
      <path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  cex: (
    <>
      <path d="M12 3 2 20h20z" />
      <path d="M12 10v4" />
      <path d="M12 17h.01" />
    </>
  ),
  replay: (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5" />
    </>
  ),
  versions: (
    <>
      <path d="m12 3 9 5-9 5-9-5z" />
      <path d="m3 13 9 5 9-5" />
    </>
  ),
  scene: (
    <>
      <path d="m12 2 9 5v10l-9 5-9-5V7z" />
      <path d="m3 7 9 5 9-5" />
      <path d="M12 12v10" />
    </>
  ),
  regress: (
    <>
      <path d="M9 3h6" />
      <path d="M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3" />
    </>
  ),
};

function Icon({ d }: { d: ReactNode }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {d}
    </svg>
  );
}

export default function App() {
  const route = useRoute();
  const describe = useAsync(api.describe, "describe");
  const runs = useAsync(api.runs, "runs");

  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const setFlag = useCallback((k: string, v: boolean) => {
    setFlags((f) => (f[k] === v ? f : { ...f, [k]: v }));
  }, []);
  const [header, setHeader] = useState<{ crumb: string; sut?: string | null }>({ crumb: "" });
  // Phones: the nav is a drawer behind the menu button; any navigation closes it.
  const [navOpen, setNavOpen] = useState(false);
  const routeKey = route.join("/");
  useEffect(() => setNavOpen(false), [routeKey]);

  const cexIds = useMemo(() => {
    const out: string[] = [];
    for (const r of runs.data?.runs ?? []) for (const c of r?.counterexamples ?? []) if (c && !out.includes(c)) out.push(c);
    return out;
  }, [runs.data]);

  const shared: Shared = {
    describe: describe.data,
    describeError: describe.error,
    runs: runs.data,
    runsError: runs.error,
    cexIds,
    reload: () => {
      describe.reload();
      runs.reload();
    },
  };

  const [rawPage, id, sub] = route;
  // The hosted demo lands on the 3D replay; locally the default stays the spec.
  const page = SITE_MODE && !window.location.hash ? "scene" : rawPage;
  const pages: { key: string; label: string; icon: ReactNode; to: string; count?: number }[] = [
    { key: "spec", label: "Spec", icon: I.spec, to: href("spec") },
    { key: "checks", label: "Checks", icon: I.checks, to: href("checks") },
    { key: "cex", label: "Counterexamples", icon: I.cex, to: href("cex", page === "cex" || page === "replay" || page === "versions" || page === "regress" ? id : null), count: cexIds.length },
    { key: "replay", label: "Replay", icon: I.replay, to: href("replay", page === "cex" || page === "versions" || page === "regress" ? id : null) },
    { key: "scene", label: "3D Replay", icon: I.scene, to: href("scene", page === "cex" || page === "replay" || page === "versions" || page === "regress" ? id : null) },
    { key: "versions", label: "Versions", icon: I.versions, to: href("versions", page === "cex" || page === "replay" || page === "regress" ? id : null) },
    { key: "regress", label: "Regressions", icon: I.regress, to: href("regress", page === "cex" || page === "replay" || page === "versions" ? id : null) },
  ];

  let screen: ReactNode;
  switch (page) {
    case "checks":
      screen = <ChecksScreen shared={shared} runId={id ?? null} />;
      break;
    case "cex":
      screen = <CexScreen shared={shared} cexId={id ?? cexIds[0] ?? null} />;
      break;
    case "replay":
      screen = <ReplayScreen shared={shared} cexId={id ?? cexIds[0] ?? null} />;
      break;
    case "versions":
      screen = <VersionsScreen shared={shared} cexId={id ?? cexIds[0] ?? null} />;
      break;
    case "scene":
      screen = (
        <Suspense fallback={<Loading lines={5} />}>
          <SceneScreen shared={shared} cexId={id ?? cexIds[0] ?? null} atMs={sub !== undefined && /^\d+$/.test(sub) ? Number(sub) : null} />
        </Suspense>
      );
      break;
    case "regress":
      screen = <RegressScreen shared={shared} cexId={id ?? null} />;
      break;
    default:
      screen = <SpecScreen shared={shared} />;
  }

  const anyFixture = Object.values(flags).some(Boolean);
  const modelName = describe.data?.model?.name;
  const sutPill = header.sut === undefined ? describe.data?.sut?.id : header.sut;

  return (
    <FixtureCtx.Provider value={setFlag}>
      <HeaderCtx.Provider value={setHeader}>
        <SharedFlags describe={describe.data} runs={runs.data} />
        <div className={`app${navOpen ? " nav-open" : ""}`}>
          <header className="topbar">
            <button type="button" className="nav-toggle" aria-label={navOpen ? "Close menu" : "Open menu"} aria-expanded={navOpen} aria-controls="primary-nav" onClick={() => setNavOpen((o) => !o)}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                {navOpen ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
              </svg>
            </button>
            <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
              <rect x="1" y="1" width="24" height="24" rx="7" fill="#7AA2FF" />
              <path d="M5 14h4l2-6 4 11 2-5h4" stroke="#0D1015" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span className="brand">FleetFlight</span>
            <span className="vsep" />
            <span className="crumb">{[modelName ?? "—", header.crumb].filter(Boolean).join(" / ")}</span>
            <div className="topbar-right">
              {sutPill && <span className="pill-sut">SUT · {sutPill.includes("@") ? `${sutPill.split("@")[0]} ${sutVersion(sutPill)}` : sutPill}</span>}
              {anyFixture && (
                <span className="badge-mock" title="At least one payload on this page has _fixture: true">
                  MOCK DATA
                </span>
              )}
            </div>
          </header>
          {SITE_MODE && <SiteBanner />}
          <div className="body">
            {navOpen && <div className="nav-backdrop" onClick={() => setNavOpen(false)} aria-hidden="true" />}
            <nav className="nav" id="primary-nav" aria-label="Primary">
              <div className="nav-h">VERIFY</div>
              {pages.map((p) => (
                <a key={p.key} href={p.to} aria-current={(page ?? "spec") === p.key ? "page" : undefined}>
                  <Icon d={p.icon} />
                  {p.label}
                  {!!p.count && <span className="nav-count" aria-label={`${p.count} counterexamples`}>{p.count}</span>}
                </a>
              ))}
              <div className="backend" aria-label="Model backend">
                <div className="nav-h" style={{ padding: 0 }}>MODEL BACKEND</div>
                <div className="backend-row on"><span className="dot" />Behavioral<span className="tag">ACTIVE</span></div>
                <div className="backend-row"><span className="dot" />PLECS / SIL<span className="tag">ROADMAP</span></div>
                <div className="backend-row"><span className="dot" />HIL · RT Box<span className="tag">ROADMAP</span></div>
                <div className="backend-row"><span className="dot" />Physical HW<span className="tag">ROADMAP</span></div>
              </div>
            </nav>
            <main className="main" key={route.join("/")}>
              {screen}
            </main>
          </div>
        </div>
      </HeaderCtx.Provider>
    </FixtureCtx.Provider>
  );
}

function SharedFlags({ describe, runs }: { describe: Describe | null; runs: RunList | null }) {
  useFixtureFlag("describe", describe);
  useFixtureFlag("runs", runs);
  return null;
}

function SiteBanner() {
  const meta = useAsync(api.meta, "meta");
  const when = meta.data?.checked_at ? new Date(meta.data.checked_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : null;
  return (
    <div className="site-banner" role="note">
      <b>Live demo.</b>
      <span>
        Model-check results are a snapshot of a real run{when && ` on ${when}`}
        {meta.data?.commit && <span className="mono faint"> ({meta.data.commit})</span>}. Replays run live through the same transition code.
      </span>
      {REPO_URL && (
        <a href={REPO_URL} target="_blank" rel="noreferrer">
          Run the checker yourself →
        </a>
      )}
    </div>
  );
}
