"use client";

import { useState } from "react";
import {
  Compass,
  FileText,
  HelpCircle,
  Plus,
  Sparkles,
  Trophy,
} from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import type { RecommendationResponse, RecommendationVideo } from "../../lib/types";
import { Button, ButtonLink } from "../ui/Button";
import { ErrorState, SkeletonText } from "../ui/Feedback";
import { VideoResourceCard } from "../resources/VideoResourceCard";
import { VideoPlayerModal } from "../resources/VideoPlayerModal";
import { StudentSuggestVideoModal } from "../resources/StudentSuggestVideoModal";

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
  const [activeVideo, setActiveVideo] = useState<RecommendationVideo | null>(null);
  const [suggestOpen, setSuggestOpen] = useState(false);

  if (rec.error) {
    return (
      <ErrorState
        title="Couldn't load help for this topic"
        message={rec.error}
        onRetry={rec.reload}
        className="mt-4"
      />
    );
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
  const hasNotes = (data.notes || []).length > 0;
  const hasVideos = (data.videos || []).length > 0;
  const hasSections = (data.sections || []).length > 0;

  return (
    <div className="mt-4 rounded-xl border border-subtle bg-surface-muted/50 p-4">
      {/* Top Banner based on Mode */}
      {data.mode === "ai_session" && (
        <div className="mb-4 flex flex-col gap-3 rounded-xl border border-accent-secondary/30 bg-accent-secondary/8 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-secondary/15 text-accent-secondary"
              aria-hidden
            >
              <Compass className="h-4 w-4" />
            </span>
            <div>
              <h4 className="text-sm font-semibold text-primary">Work through it together</h4>
              <p className="mt-0.5 text-xs text-secondary">
                {data.reason ||
                  "This topic needs a guided walkthrough. A 1:1 Socratic session will take you through it step by step."}
              </p>
            </div>
          </div>
          <ButtonLink href={guidedSessionHref(topic)} variant="accent" className="shrink-0 text-xs">
            Start guided session
          </ButtonLink>
        </div>
      )}

      {(data.mode === "diagnostic" || data.mode === "verification") && (
        <div className="mb-4 flex flex-col gap-3 rounded-xl border border-accent-secondary/30 bg-accent-secondary/8 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-secondary/15 text-accent-secondary"
              aria-hidden
            >
              <HelpCircle className="h-4 w-4" />
            </span>
            <div>
              <h4 className="text-sm font-semibold text-primary">
                {data.mode === "diagnostic" ? "Diagnostic check recommended" : "Verification check"}
              </h4>
              <p className="mt-0.5 text-xs text-secondary">
                {data.reason || "Take a short quiz to calibrate where your understanding stands."}
              </p>
            </div>
          </div>
          <ButtonLink href="/quiz" variant="accent" className="shrink-0 text-xs">
            Take topic quiz
          </ButtonLink>
        </div>
      )}

      {data.mode === "advance" && (
        <div className="mb-4 flex flex-col gap-3 rounded-xl border border-success/30 bg-success/8 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-success/15 text-success"
              aria-hidden
            >
              <Trophy className="h-4 w-4" />
            </span>
            <div>
              <h4 className="text-sm font-semibold text-primary">Demonstrated Mastery</h4>
              <p className="mt-0.5 text-xs text-secondary">
                {data.reason || "Solid understanding demonstrated. Explore advanced resources or take a challenge quiz."}
              </p>
            </div>
          </div>
          <ButtonLink href="/quiz" variant="secondary" className="shrink-0 text-xs">
            Challenge quiz
          </ButtonLink>
        </div>
      )}

      {/* Resource Sections Header */}
      <div className="flex items-center justify-between pb-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-tertiary">
          Recommended Learning Resources
        </h4>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setSuggestOpen(true)}
          icon={<Plus className="h-3 w-3" />}
          className="text-xs"
        >
          Suggest video
        </Button>
      </div>

      {!hasSections && !hasVideos && !hasNotes ? (
        <p className="py-2 text-xs text-tertiary">
          No external resources logged for this topic yet. You can suggest a helpful YouTube video or ask the tutor.
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {/* YouTube Video Resources */}
          {hasVideos && (
            <div>
              <div className="flex flex-col gap-2">
                {data.videos.map((v) => (
                  <VideoResourceCard
                    key={v.video_id}
                    video={v}
                    onPlay={(vid) => setActiveVideo(vid)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Course Material Chunks */}
          {hasSections && (
            <div>
              <p className="mb-2 text-xs font-medium text-tertiary">From your course curriculum</p>
              <ul className="flex flex-col gap-2">
                {data.sections.map((s) => (
                  <li
                    key={s.chunk_id}
                    className="rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-secondary"
                  >
                    {truncate(s.text, 240)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Peer & Educator Notes */}
          {hasNotes && (
            <div>
              <p className="mb-2 text-xs font-medium text-tertiary">Shared Notes</p>
              <ul className="flex flex-col gap-2">
                {(data.notes || []).map((n) => (
                  <li key={n.resource_id} className="rounded-lg border border-subtle bg-surface p-3 text-xs">
                    <div className="flex items-center gap-1.5 font-medium text-primary">
                      <FileText className="h-3.5 w-3.5 text-accent-secondary" />
                      <span>{n.title}</span>
                      <span className="text-[10px] text-tertiary">· {n.author_role}</span>
                    </div>
                    <p className="mt-1 text-secondary whitespace-pre-wrap">{truncate(n.content, 260)}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Interactive Video Player Modal */}
      <VideoPlayerModal video={activeVideo} onClose={() => setActiveVideo(null)} />

      {/* Student Suggestion Modal */}
      <StudentSuggestVideoModal
        open={suggestOpen}
        onClose={() => setSuggestOpen(false)}
        classId={classId}
        topic={topic}
        onSuggested={rec.reload}
      />
    </div>
  );
}
