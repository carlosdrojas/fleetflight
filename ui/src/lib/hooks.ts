import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export interface Async<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Run `fn` when `key` changes. `key === null` means "nothing to load". */
export function useAsync<T>(fn: () => Promise<T>, key: string | null): Async<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>({
    data: null,
    error: null,
    loading: key !== null,
  });
  const [nonce, setNonce] = useState(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  useEffect(() => {
    if (key === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let live = true;
    setState((s) => ({ data: s.data, error: null, loading: true }));
    fnRef.current().then(
      (data) => live && setState({ data, error: null, loading: false }),
      (e: unknown) => live && setState({ data: null, error: e instanceof Error ? e.message : String(e), loading: false }),
    );
    return () => {
      live = false;
    };
  }, [key, nonce]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...state, reload };
}

/** Hash router: "#/cex/abc" → ["cex", "abc"]. */
export function useRoute(): string[] {
  const read = () =>
    (window.location.hash.replace(/^#\/?/, "") || "spec").split("/").filter(Boolean).map(decodeURIComponent);
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export const href = (...parts: (string | undefined | null)[]) =>
  "#/" + parts.filter((p): p is string => !!p).map(encodeURIComponent).join("/");

/** Pages report which of their payloads are fixtures; the top bar shows MOCK DATA only if one is. */
export const FixtureCtx = createContext<(key: string, isFixture: boolean) => void>(() => {});

export function useFixtureFlag(key: string, payload: { _fixture?: unknown } | null | undefined) {
  const set = useContext(FixtureCtx);
  const flag = payload?._fixture === true;
  useEffect(() => {
    set(key, flag);
    return () => set(key, false);
  }, [key, flag, set]);
}

/** Page header context: breadcrumb and SUT pill text. */
export const HeaderCtx = createContext<(h: { crumb: string; sut?: string | null }) => void>(() => {});

export function useHeader(crumb: string, sut?: string | null) {
  const set = useContext(HeaderCtx);
  useEffect(() => {
    set({ crumb, sut });
  }, [crumb, sut, set]);
}
