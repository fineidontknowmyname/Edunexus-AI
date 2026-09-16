"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "../../lib/api";
import type { RecommendationResponse } from "../../lib/types";
import { Card } from "../ui/Card";
import { Button } from "../ui/Button";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function RecommendationPanel({ classId, topic }: { classId: string; topic: string }) {
  const router = useRouter();
  const [data, setData] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    apiFetch<RecommendationResponse>(`/recommendations?topic=${encodeURIComponent(topic)}&class_id=${classId}`)
      .then(setData)
      .catch(() => setError("Couldn't load recommendations right now."));
  }, [classId, topic]);

  if (error) {
    return (
      <Card className="mt-2">
        <p className="text-sm text-tertiary">{error}</p>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card className="mt-2">
        <p className="text-sm text-tertiary">Loading recommendations…</p>
      </Card>
    );
  }

  return (
    <Card className="mt-2">
      {data.mode === "static" ? (
        <div>
          <h3 className="font-semibold text-primary mb-2 text-sm">Explore on your own</h3>
          {data.sections.length === 0 && data.videos.length === 0 ? (
            <p className="text-sm text-tertiary">No extra resources found for this topic yet.</p>
          ) : (
            <>
              {data.sections.length > 0 && (
                <div className="flex flex-col gap-2 mb-3">
                  {data.sections.map((s) => (
                    <p key={s.chunk_id} className="text-sm text-secondary">
                      {truncate(s.text, 220)}
                    </p>
                  ))}
                </div>
              )}
              {data.videos.length > 0 && (
                <div className="flex flex-col gap-1">
                  {data.videos.map((v) => (
                    <a
                      key={v.video_id}
                      href={v.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-accent-secondary hover:underline"
                    >
                      {v.title} — {v.channel}
                    </a>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      ) : (
        <div>
          <h3 className="font-semibold text-primary mb-1 text-sm">Work through it together</h3>
          <p className="text-sm text-tertiary mb-3">
            This topic needs a guided walkthrough — start a 1:1 Socratic session to work through it step by step.
          </p>
          <Button
            onClick={() =>
              router.push(`/chat?topic=${encodeURIComponent(data.socratic_seed_message ?? topic)}&mode=socratic`)
            }
          >
            Start guided session
          </Button>
        </div>
      )}
    </Card>
  );
}
