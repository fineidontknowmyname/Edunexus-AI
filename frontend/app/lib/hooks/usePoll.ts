"use client";

import { useEffect, useRef, useState } from "react";

interface UsePollOptions<T> {
  intervalMs?: number;
  /** Stop polling once this returns true for the latest result. */
  until?: (data: T) => boolean;
  enabled?: boolean;
}

interface UsePollState<T> {
  data: T | null;
  error: string | null;
  isPolling: boolean;
}

/**
 * Repeatedly calls `fetcher` on an interval until `until(data)` returns true
 * (or the component unmounts / `enabled` goes false). Used for job status
 * polling (e.g. GET /documents/status/{job_id}) per the plan's "poll every 3s"
 * upload UX — SSE is reserved for the chat stream in Chunk 2.
 */
export function usePoll<T>(
  fetcher: () => Promise<T>,
  { intervalMs = 3000, until, enabled = true }: UsePollOptions<T> = {}
): UsePollState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(enabled);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function tick() {
      try {
        const result = await fetcherRef.current();
        if (cancelled) return;
        setData(result);
        setError(null);

        if (until?.(result)) {
          setIsPolling(false);
          return;
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Polling failed");
      }
      if (!cancelled) {
        timer = setTimeout(tick, intervalMs);
      }
    }

    setIsPolling(true);
    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, intervalMs]);

  return { data, error, isPolling };
}
