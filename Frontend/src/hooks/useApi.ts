"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, NetworkError, isAbort } from "@/lib/api";

export type ApiPhase = "idle" | "loading" | "success" | "error";

export interface ApiState<T> {
  data: T | null;
  error: Error | null;
  phase: ApiPhase;
  /** True on the first load only, so a refresh doesn't blank the screen. */
  isInitialLoad: boolean;
  /** True while a refetch runs over data that is already on screen. */
  isRefreshing: boolean;
  refresh: () => void;
}

interface Settled<T> {
  /** The request this result belongs to. */
  id: string;
  data: T | null;
  error: Error | null;
}

/**
 * Abortable fetch that discards stale responses.
 *
 * Each request has an identity derived during render from the fetcher and the
 * refresh counter. A result is stored together with the identity that produced
 * it, so "loading" is *derived* — the settled identity differs from the current
 * one — rather than written from inside the effect. Out-of-order responses from
 * a superseded request are dropped, and nothing writes after unmount.
 *
 * `fetcher` must be stable (useCallback) — it is the request identity.
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  opts: { enabled?: boolean } = {},
): ApiState<T> {
  const enabled = opts.enabled ?? true;

  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  // A new fetcher identity is a new request. This is React's "adjust state when
  // props change" pattern: the update happens during render, React re-runs this
  // component before committing, and the effect below sees the new id.
  // `useState(() => fetcher)` is required — a bare function argument would be
  // read as a lazy initializer.
  const [seenFetcher, setSeenFetcher] = useState(() => fetcher);
  const [generation, setGeneration] = useState(0);
  if (seenFetcher !== fetcher) {
    setSeenFetcher(() => fetcher);
    setGeneration((g) => g + 1);
  }
  const requestId = `${generation}:${nonce}`;

  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;

    const id = requestId;
    const controller = new AbortController();

    // Cleanup aborts, so a superseded request rejects with AbortError and never
    // writes. A response already queued when cleanup ran lands under its own
    // (older) id, which still reads as stale and is overwritten by the newer one.
    fetcher(controller.signal)
      .then((data) => {
        if (!mounted.current) return;
        setSettled({ id, data, error: null });
      })
      .catch((caught: unknown) => {
        if (isAbort(caught) || !mounted.current) return;
        // Keep the data already on screen; the error is reported alongside it.
        setSettled((prev) => ({ id, data: prev?.data ?? null, error: toError(caught) }));
      });

    return () => controller.abort();
  }, [fetcher, enabled, requestId]);

  const loading = enabled && settled?.id !== requestId;
  const phase: ApiPhase = !enabled
    ? "idle"
    : loading
      ? "loading"
      : settled?.error
        ? "error"
        : "success";

  const data = settled?.data ?? null;
  const error = loading ? null : (settled?.error ?? null);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return {
    data,
    error,
    phase,
    isInitialLoad: loading && data === null,
    isRefreshing: loading && data !== null,
    refresh,
  };
}

/**
 * A mutation with explicit success and failure. Never fails silently: the
 * caller gets the error object back so it can name a reason in a Toast.
 */
export function useMutation<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
) {
  const [pending, setPending] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (...args: TArgs): Promise<{ ok: true; data: TResult } | { ok: false; error: Error }> => {
      setPending(true);
      try {
        const data = await action(...args);
        return { ok: true, data };
      } catch (caught) {
        return { ok: false, error: toError(caught) };
      } finally {
        if (mounted.current) setPending(false);
      }
    },
    [action],
  );

  return { run, pending };
}

function toError(caught: unknown): Error {
  if (caught instanceof Error) return caught;
  return new Error(String(caught));
}

/** Human-readable reason for a failure, naming the status and path. */
export function describeError(error: Error | null): string {
  if (!error) return "";
  if (error instanceof ApiError) {
    return error.detail
      ? `${error.method} ${error.path} returned ${error.status} — ${error.detail}`
      : `${error.method} ${error.path} returned ${error.status}.`;
  }
  if (error instanceof NetworkError) {
    return `Couldn't reach the backend at ${error.base}. Is the FastAPI server running?`;
  }
  return error.message || "The request failed and gave no reason.";
}
