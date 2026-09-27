import type { ReactNode } from "react";

export function Loading({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card" aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skel" style={{ width: `${90 - i * 17}%` }} />
      ))}
    </div>
  );
}

export function ErrorState({ title, error, onRetry }: { title: string; error: string; onRetry?: () => void }) {
  return (
    <div className="state err" role="alert">
      <b>{title}</b>
      <span className="mono">{error}</span>
      {onRetry && (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state">{children}</div>;
}

export function Result({ r }: { r: string | undefined | null }) {
  if (r === "PASS") return <span className="mono t-pass" style={{ fontWeight: 600 }}>✓ PASS</span>;
  if (r === "FAIL") return <span className="mono t-fail" style={{ fontWeight: 600 }}>✕ FAIL</span>;
  return <span className="mono muted">{r || "—"}</span>;
}

export function PlayIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M7 4v16l13-8z" />
    </svg>
  );
}

export function AssumptionRow({ text }: { text: string }) {
  const m = /^(ASSUMED|OUT OF SCOPE)\s+(.*)$/s.exec(text ?? "");
  const tag = m?.[1] ?? "";
  const body = m?.[2] ?? text;
  return (
    <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 13 }}>
      <span className={tag === "OUT OF SCOPE" ? "tag-oos" : "tag-assumed"}>{tag || "UNTAGGED"}</span>
      <span>{body}</span>
    </div>
  );
}
