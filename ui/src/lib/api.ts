import type { CheckReport, Counterexample, Describe, RegressList, RegressSource, ReplayResult, RunList, SiteMeta } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

/**
 * Site mode (VITE_FF_STATIC=1, the hosted demo): GETs read the exported run in ./data/
 * (scripts/export_site.py); replay calls the live function and falls back to the exported replay.
 */
export const SITE_MODE = import.meta.env.VITE_FF_STATIC === "1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const url = SITE_MODE && (init?.method ?? "GET") === "GET" ? `./data${path}.json` : `./api${path}`;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError(`cannot reach the API (${(e as Error).message}). Is \`fleetflight serve\` running?`, 0);
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const msg =
      (body && typeof body === "object" && "error" in body && String((body as { error: unknown }).error)) ||
      text.slice(0, 200) ||
      res.statusText;
    throw new ApiError(`${res.status} ${msg}`, res.status);
  }
  if (body === null || typeof body !== "object") throw new ApiError(`GET ${path}: response is not JSON`, res.status);
  return body as T;
}

export const api = {
  describe: () => request<Describe>("/describe"),
  runs: () => request<RunList>("/runs"),
  run: (id: string) => request<CheckReport>(`/runs/${encodeURIComponent(id)}`),
  cex: (id: string) => request<Counterexample>(`/cex/${encodeURIComponent(id)}`),
  replay: async (cex: string, sut: string): Promise<ReplayResult> => {
    const live = () =>
      request<ReplayResult>("/replay", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cex, sut }),
      });
    if (!SITE_MODE) return live();
    try {
      return await live();
    } catch (e) {
      // Bad input is a real error; anything else (no function, cold-start failure) uses the export.
      if (e instanceof ApiError && e.status === 400) throw e;
      const version = sut.includes("@") ? sut.split("@")[1] : sut;
      return { ...(await request<ReplayResult>(`/replay/${encodeURIComponent(cex)}__${encodeURIComponent(version)}`)), _snapshot: true };
    }
  },
  meta: () => request<SiteMeta>("/meta"),
  regressList: () => request<RegressList>("/regress"),
  regressSource: (cex: string) => request<RegressSource>(`/regress/${encodeURIComponent(cex)}`),
};
