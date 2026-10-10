"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { errorMessage } from "../api";

interface UsePollOptions<T> {
  intervalMs?: number;
  until?: (data: T) => boolean;
}

interface PollState<T> {
  key: string | null;
  data: T | null;
  error: string | null;
}

export function usePoll<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  { intervalMs = 3000, until }: UsePollOptions<T> = {}
): { data: T | null; error: string | null } {
  const [state, setState] = useState<PollState<T>>({ key: null, data: null, error: null });
  const fetchOnce = useEffectEvent(() => fetcher());
  const isDone = useEffectEvent((result: T) => until?.(result) ?? false);

  useEffect(() => {
    if (key === null) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const result = await fetchOnce();
        if (cancelled) return;
        setState({ key, data: result, error: null });
        if (isDone(result)) return;
      } catch (err) {
        if (cancelled) return;
        setState((prev) => ({ key, data: prev.key === key ? prev.data : null, error: errorMessage(err, "Polling failed") }));
      }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    }

    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [key, intervalMs]);

  return state.key === key ? { data: state.data, error: state.error } : { data: null, error: null };
}
