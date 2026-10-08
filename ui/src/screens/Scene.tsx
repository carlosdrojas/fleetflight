import { useEffect, useMemo, useRef, useState } from "react";
import type { Shared } from "../App";
import { Empty, ErrorState, Loading } from "../components/ui";
import { SceneView } from "../components/sceneView";
import { api } from "../lib/api";
import { href, useAsync, useFixtureFlag, useHeader } from "../lib/hooks";
import { buildTimeline, frameAt, timerAt, type Timeline } from "../lib/scene";
import type { Counterexample, ReplayResult } from "../lib/types";
import { num, sutVersion } from "../lib/trace";

// 3D replay: the same counterexample played on several firmware versions side by side,
// on one shared clock. Every visual is driven by the replay trace (lib/scene.ts).

const SPEEDS = [0.1, 0.25, 0.5, 1];

type Panel = { sut: string; state: "loading" | "ok" | "error"; r?: ReplayResult; tl?: Timeline; error?: string };

export default function SceneScreen({ shared, cexId, atMs }: { shared: Shared; cexId: string | null; atMs?: number | null }) {
  const cex = useAsync(() => api.cex(cexId as string), cexId);
  useFixtureFlag("cex", cex.data);
  useHeader(cexId ? `3d / ${cexId}` : "3d", null);
  if (!cexId) return <Empty>No counterexample to play. Run a check first.</Empty>;
  if (shared.describeError) return <ErrorState title="Could not load the SUT versions (describe)" error={shared.describeError} onRetry={shared.reload} />;
  if (cex.error) return <ErrorState title={`Could not load ${cexId}`} error={cex.error} onRetry={cex.reload} />;
  if (!cex.data || !shared.describe) return <Loading lines={5} />;
  return <SceneBody shared={shared} cex={cex.data} cexId={cexId} atMs={atMs ?? null} />;
}

function SceneBody({ shared, cex, cexId, atMs }: { shared: Shared; cex: Counterexample; cexId: string; atMs: number | null }) {
  const versions = useMemo(() => (shared.describe?.sut_versions ?? []).filter((v): v is string => typeof v === "string"), [shared.describe]);
  const [picked, setPicked] = useState<string[]>(() => (versions.length > 1 ? [versions[0], versions[versions.length - 1]] : versions));
  const [panels, setPanels] = useState<Panel[]>([]);
  const inv = cex.invariant;
  const bound = num(inv?.bound_ms);
  const timerKey = inv?.timer_key ?? null;

  useEffect(() => {
    let live = true;
    setPanels(picked.map((sut) => ({ sut, state: "loading" })));
    picked.forEach((sut, i) => {
      api.replay(cexId, sut).then(
        (r) => live && setPanels((ps) => ps.map((p, j) => (j === i ? { sut, state: "ok", r, tl: buildTimeline(r, timerKey) } : p))),
        (e: Error) => live && setPanels((ps) => ps.map((p, j) => (j === i ? { sut, state: "error", error: e.message } : p))),
      );
    });
    return () => {
      live = false;
    };
  }, [picked, cexId, timerKey]);
  useFixtureFlag("scene", panels.some((p) => p.r?._fixture === true) ? { _fixture: true } : null);

  const endMs = Math.max(400, ...panels.map((p) => p.tl?.endMs ?? 0));

  // One clock for every panel. The rAF loop writes t into a ref (for the 3D views) and
  // into state a few times a second (for the HUD text and the scrubber).
  // #/scene/<cex>/<ms> opens paused at that instant (for screenshots and deep links).
  const [playing, setPlaying] = useState(atMs === null);
  const [speed, setSpeed] = useState(0.25);
  const [t, setT] = useState(atMs ?? 0);
  const tRef = useRef(atMs ?? 0);
  const views = useRef(new Map<string, SceneView>());
  const playRef = useRef(playing);
  playRef.current = playing;
  const speedRef = useRef(speed);
  speedRef.current = speed;
  const endRef = useRef(endMs);
  endRef.current = endMs;

  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    let hudAt = 0;
    const loop = (now: number) => {
      // Clamp: after a hidden tab (or a throttled frame) don't jump the story ahead.
      const dt = Math.min(now - last, 100);
      last = now;
      if (playRef.current) {
        let next = tRef.current + dt * speedRef.current;
        // Hold on the last frame for a beat, then loop.
        if (next > endRef.current + 900 * speedRef.current) next = 0;
        tRef.current = next;
      }
      const shown = Math.min(tRef.current, endRef.current);
      for (const v of views.current.values()) v.render(shown);
      if (now - hudAt > 60) {
        hudAt = now;
        setT(shown);
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  const seek = (v: number) => {
    tRef.current = v;
    setT(v);
  };

  const toggle = (sut: string) =>
    setPicked((p) => (p.includes(sut) ? (p.length > 1 ? p.filter((x) => x !== sut) : p) : versions.filter((v) => p.includes(v) || v === sut)));

  const moves = (cex.moves ?? []).map((m) => m?.move?.label ?? m?.move?.name).filter(Boolean).join(" · ");

  return (
    <>
      <div className="ph">
        <div className="ph-text">
          <h1>3D replay · {cexId}</h1>
          <span className="muted">
            Injected: <span className="mono">{moves || "—"}</span>
            {inv?.id && ` · watching ${inv.id}${bound !== null ? ` (budget ${bound} ms)` : ""}`}
          </span>
        </div>
        <div className="ph-actions">
          <div className="seg" role="group" aria-label="Counterexample">
            {shared.cexIds.map((id) => (
              <a key={id} className={`seg-b${id === cexId ? " on" : ""}`} href={href("scene", id)}>
                {id}
              </a>
            ))}
          </div>
        </div>
      </div>

      <div className="scene-bar">
        <button type="button" className="btn btn-sm" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <button type="button" className="btn btn-sm" onClick={() => seek(0)}>
          ↺ Restart
        </button>
        <input
          className="scene-scrub"
          type="range"
          min={0}
          max={endMs}
          step={10}
          value={Math.round(t)}
          onChange={(e) => {
            setPlaying(false);
            seek(Number(e.target.value));
          }}
          aria-label="Simulated time"
        />
        <span className="mono scene-clock">t = {Math.round(t)} ms</span>
        <div className="seg" role="group" aria-label="Speed">
          {SPEEDS.map((s) => (
            <button key={s} type="button" className={`seg-b${s === speed ? " on" : ""}`} onClick={() => setSpeed(s)}>
              {s}×
            </button>
          ))}
        </div>
        <div className="seg" role="group" aria-label="Firmware versions">
          {versions.map((v) => (
            <button key={v} type="button" className={`seg-b${picked.includes(v) ? " on" : ""}`} onClick={() => toggle(v)}>
              {sutVersion(v)}
            </button>
          ))}
        </div>
      </div>

      <div className="scene-grid" style={{ gridTemplateColumns: `repeat(${Math.max(panels.length, 1)}, minmax(0, 1fr))` }}>
        {panels.map((p) => (
          <ScenePanel key={p.sut} panel={p} t={t} bound={bound} views={views.current} invId={inv?.id ?? null} />
        ))}
      </div>
      <p className="faint small" style={{ marginTop: 10 }}>
        Each panel is a live replay of the counterexample through the real transition code (POST /api/replay). Drag to orbit, scroll to zoom. Simulated time runs at {speed}× real time.
      </p>
    </>
  );
}

function ScenePanel({ panel, t, bound, views, invId }: { panel: Panel; t: number; bound: number | null; views: Map<string, SceneView>; invId: string | null }) {
  const host = useRef<HTMLDivElement>(null);
  const { sut, tl, r } = panel;

  useEffect(() => {
    if (!host.current || !tl) return;
    const v = new SceneView(host.current);
    v.setTimeline(tl);
    views.set(sut, v);
    return () => {
      views.delete(sut);
      v.dispose();
    };
  }, [sut, tl, views]);

  const fr = tl ? frameAt(tl, t) : null;
  const timer = tl ? timerAt(tl, t) : { elapsed: null, stopped: false };
  const elapsed = timer.elapsed;
  const over = elapsed !== null && bound !== null && elapsed >= bound;
  const violating = (fr?.violations.length ?? 0) > 0;
  const recent = (tl?.captions ?? []).filter((c) => c.t <= t).slice(-4);
  const windowMs = num(r?.violation_window_ms?.duration_ms);

  return (
    <div className={`scene-panel${violating ? " is-fail" : ""}`}>
      <div className="scene-canvas" ref={host} />
      <div className="scene-hud-top">
        <span className="scene-ver">{sutVersion(sut)}</span>
        {r?.verdict && <span className={r.verdict === "PASS" ? "chip-pass" : "chip-fail"}>{r.verdict}</span>}
        {windowMs !== null && <span className="faint small mono">fault→stop {windowMs} ms</span>}
      </div>
      {panel.state === "loading" && <div className="scene-overlay muted">Replaying {sutVersion(sut)}…</div>}
      {panel.state === "error" && <div className="scene-overlay t-fail">{panel.error}</div>}
      {violating && (
        <div className="scene-alert" role="status">
          {fr?.violations.join(", ")} violated · inverter {fr?.inv.split(" ").slice(0, 2).join(" ")}
        </div>
      )}
      <div className="scene-hud-bottom">
        <ol className="scene-log">
          {recent.map((c, i) => (
            <li key={`${c.t}-${i}`} className={`tone-${c.tone}`}>
              <span className="mono faint">{c.t} ms</span> {c.text}
            </li>
          ))}
        </ol>
        {bound !== null && (
          <div className="scene-timer" aria-label={`${invId ?? "invariant"} timer`}>
            <div className="scene-timer-h">
              <span>{invId} fault → stop</span>
              <span className={`mono ${over ? "t-fail" : timer.stopped ? "t-pass" : elapsed !== null ? "t-warn" : "faint"}`}>
                {elapsed === null ? "—" : timer.stopped ? `stopped at ${elapsed} ms` : `${elapsed} / ${bound} ms`}
              </span>
            </div>
            <div className="scene-timer-track">
              <div
                className={`scene-timer-fill${over ? " over" : timer.stopped ? " done" : ""}`}
                style={{ width: `${elapsed === null ? 0 : Math.min(100, (elapsed / (bound * 2.2)) * 100)}%` }}
              />
              <div className="scene-timer-budget" style={{ left: `${100 / 2.2}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
