import type { CheckReport, Counterexample, Describe, RegressList, RegressSource, ReplayResult, RunList } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`./api${path}`, init);
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
  replay: (cex: string, sut: string) =>
    request<ReplayResult>("/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cex, sut }),
    }),
  regressList: () => request<RegressList>("/regress"),
  regressSource: (cex: string) => request<RegressSource>(`/regress/${encodeURIComponent(cex)}`),
};
