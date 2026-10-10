"use client";

import { useCallback, useEffect, useEffectEvent, useState } from "react";
import { apiFetch, errorMessage } from "../api";

interface AsyncState<T> {
  key: string | null;
  data: T | null;
  error: string | null;
}

export interface AsyncResult<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  mutate: (update: (prev: T | null) => T | null) => void;
}

export function useAsync<T>(key: string | null, fetcher: () => Promise<T>): AsyncResult<T> {
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState<AsyncState<T>>({ key: null, data: null, error: null });
  const requestKey = key === null ? null : `${key}::${nonce}`;
  const run = useEffectEvent(() => fetcher());

  useEffect(() => {
    if (requestKey === null) return;
    let cancelled = false;
    run().then(
      (data) => {
        if (!cancelled) setState({ key: requestKey, data, error: null });
      },
      (err: unknown) => {
        if (!cancelled) setState({ key: requestKey, data: null, error: errorMessage(err) });
      }
    );
    return () => {
      cancelled = true;
    };
  }, [requestKey]);

  const sameResource = state.key !== null && key !== null && state.key.startsWith(`${key}::`);
  const settled = state.key === requestKey;

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const mutate = useCallback(
    (update: (prev: T | null) => T | null) => setState((prev) => ({ ...prev, data: update(prev.data) })),
    []
  );

  return {
    data: sameResource ? state.data : null,
    error: settled ? state.error : null,
    loading: requestKey !== null && !settled,
    reload,
    mutate,
  };
}

export function useApi<T>(path: string | null): AsyncResult<T> {
  return useAsync<T>(path, () => apiFetch<T>(path as string));
}
