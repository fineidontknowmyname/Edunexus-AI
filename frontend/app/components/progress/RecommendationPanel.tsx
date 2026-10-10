"use client";

import { Compass, ExternalLink, PlayCircle } from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import type { RecommendationResponse } from "../../lib/types";
import { ButtonLink } from "../ui/Button";
import { ErrorState, SkeletonText } from "../ui/Feedback";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

export function guidedSessionHref(topic: string): string {
  return `/chat?topic=${encodeURIComponent(topic)}&mode=socratic`;
}

export function RecommendationPanel({ classId, topic }: { classId: string; topic: string }) {
  const rec = useApi<RecommendationResponse>(
    `/recommendations?topic=${encodeURIComponent(topic)}&class_id=${classId}`
  );

  if (rec.error) {
    return <ErrorState title="Couldn't load help for this topic" message={rec.error} onRetry={rec.reload} className="mt-4" />;
  }

  if (!rec.data) {
    return (
      <div className="mt-4 rounded-lg bg-surface-muted/60 p-4" role="status">
        <span className="sr-only">Loading recommendations…</span>
        <SkeletonText lines={3} />
      </div>
    );
  }

  const data = rec.data;

  if (data.mode === "ai_session") {
    return (
      <div className="mt-4 flex flex-col gap-3 rounded-lg border border-accent-secondary/30 bg-accent-secondary/6 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-secondary/15 text-accent-secondary" aria-hidden>
            <Compass className="h-4 w-4" />
          </span>
          <div>
            <h3 className="text-sm font-semibold text-primary">Work through it together</h3>
            <p className="mt-0.5 text-sm text-secondary">
              {data.reason ||
                "This topic needs a guided walkthrough. A 1:1 Socratic session will take you through it step by step."}
            </p>
          </div>
        </div>
        <ButtonLink href={guidedSessionHref(topic)} variant="accent" className="shrink-0">
          Start guided session
        </ButtonLink>
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-lg bg-surface-muted/60 p-4">
      <h3 className="text-sm font-semibold text-primary">Explore on your own</h3>
      {data.reason && <p className="mt-0.5 text-sm text-secondary">{data.reason}</p>}
      {data.sections.length === 0 && data.videos.length === 0 ? (
        <p className="mt-1 text-sm text-tertiary">No extra resources found for this topic yet. Try asking the tutor about it.</p>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          {data.sections.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-tertiary">From your course materials</p>
              <ul className="flex flex-col gap-2">
                {data.sections.map((s) => (
                  <li key={s.chunk_id} className="rounded-md border border-subtle bg-surface px-3 py-2 text-sm text-secondary">
                    {truncate(s.text, 240)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.videos.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-tertiary">Videos</p>
              <ul className="flex flex-col gap-1.5">
                {data.videos.map((v) => (
                  <li key={v.video_id}>
                    <a
                      href={v.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-start gap-2 text-sm text-accent-secondary hover:underline"
                    >
                      <PlayCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                      <span>
                        {v.title} <span className="text-tertiary">· {v.channel}</span>
                      </span>
                      <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 opacity-60" aria-hidden />
                      <span className="sr-only">(opens in a new tab)</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
