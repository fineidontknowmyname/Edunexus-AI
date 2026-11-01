"use client";

import { useState } from "react";
import {
  Compass,
  FileText,
  HelpCircle,
  Lightbulb,
  ListChecks,
  Plus,
  Trophy,
} from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import type { RecommendationResponse, RecommendationVideo } from "../../lib/types";
import { Button, ButtonLink } from "../ui/Button";
import { ErrorState, SkeletonText } from "../ui/Feedback";
import { VideoResourceCard } from "../resources/VideoResourceCard";
import { VideoPlayerModal } from "../resources/VideoPlayerModal";
import { StudentSuggestVideoModal } from "../resources/StudentSuggestVideoModal";
import { TopicQuizPrepModal } from "../quiz/TopicQuizPrepModal";

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
  const [prepModalOpen, setPrepModalOpen] = useState(false);

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
    <div className="mt-4 rounded-[2px] border border-line bg-surface p-4">
      {/* Prerequisite Advisory Notice */}
      {data.prerequisite_advisory && (
        <div className="mb-4 flex flex-col gap-2 rounded-[2px] border border-line bg-surface2 p-3 text-xs sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="font-semibold text-ink">Prerequisite Advisory: </span>
            <span className="text-muted">{data.prerequisite_advisory.reason}</span>
          </div>
          <div className="shrink-0">
            <ButtonLink
              href={`/quiz?topic=${encodeURIComponent(data.prerequisite_advisory.topic)}`}
              variant="outline"
              size="sm"
            >
              Review {data.prerequisite_advisory.topic}
            </ButtonLink>
          </div>
        </div>
      )}

      {/* Top Banner based on Mode */}
      {data.mode === "ai_session" && (
        <div className="mb-4 flex flex-col gap-3 rounded-[2px] border border-line bg-surface2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-bg"
              aria-hidden
            >
              <Compass className="h-4 w-4" />
            </span>
            <div>
              <h4 className="font-serif text-[16px] text-ink">Work through it together</h4>
              <p className="mt-0.5 text-xs text-muted">
                {data.reason ||
                  "This topic needs a guided walkthrough. A 1:1 Socratic session will take you through it step by step."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              icon={<ListChecks className="h-3.5 w-3.5" />}
              onClick={() => setPrepModalOpen(true)}
            >
              Take a Test
            </Button>
            <ButtonLink href={guidedSessionHref(topic)} variant="primary" size="sm">
              Start guided session
            </ButtonLink>
          </div>
        </div>
      )}

      {(data.mode === "diagnostic" || data.mode === "verification") && (
        <div className="mb-4 flex flex-col gap-3 rounded-[2px] border border-line bg-surface2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-ink text-bg"
              aria-hidden
            >
              <HelpCircle className="h-4 w-4" />
            </span>
            <div>
              <h4 className="font-serif text-[16px] text-ink">
                {data.mode === "diagnostic" ? "Diagnostic check recommended" : "Verification check"}
              </h4>
              <p className="mt-0.5 text-xs text-muted">
                {data.reason || "Take a short quiz to calibrate where your understanding stands."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Button
              variant="primary"
              size="sm"
              icon={<ListChecks className="h-3.5 w-3.5" />}
              onClick={() => setPrepModalOpen(true)}
            >
              Take a Test
            </Button>
            <ButtonLink href={guidedSessionHref(topic)} variant="outline" size="sm">
              Ask Tutor
            </ButtonLink>
          </div>
        </div>
      )}

      {data.mode === "reinforce" && (
        <div className="mb-4 flex flex-col gap-3 rounded-[2px] border border-line bg-surface2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-amber text-ink"
              aria-hidden
            >
              <Lightbulb className="h-4 w-4" />
            </span>
            <div>
              <h4 className="text-sm font-semibold text-ink">
                Targeted practice recommended
              </h4>
              <p className="mt-0.5 text-xs text-muted">
                {data.reason || "You're close on this topic. A short practice quiz will help lock it in."}
              </p>
            </div>
          </div>
          <ButtonLink href={`/quiz?topic=${encodeURIComponent(topic)}`} size="sm" variant="secondary">
            Take Practice Quiz
          </ButtonLink>
        </div>
      )}

      {data.mode === "advance" && (
        <div className="mb-4 flex flex-col gap-3 rounded-[2px] border border-line bg-surface2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <span
              className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-green text-white"
              aria-hidden
            >
              <Trophy className="h-4 w-4" />
            </span>
            <div>
              <h4 className="font-serif text-[16px] text-ink">High Estimated Understanding</h4>
              <p className="mt-0.5 text-xs text-muted">
                {data.reason || "Strong performance demonstrated on recent assessments. Explore advanced resources or take a challenge quiz."}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              icon={<ListChecks className="h-3.5 w-3.5" />}
              onClick={() => setPrepModalOpen(true)}
            >
              Take a Test
            </Button>
          </div>
        </div>
      )}

      {/* Resource Sections Header */}
      <div className="flex items-center justify-between pb-2">
        <h4 className="font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
          Recommended Learning Resources
        </h4>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setSuggestOpen(true)}
          icon={<Plus className="h-3 w-3" />}
        >
          Suggest video
        </Button>
      </div>

      {!hasSections && !hasVideos && !hasNotes ? (
        <p className="py-2 font-mono text-xs text-muted">
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
              <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">From your course curriculum</p>
              <ul className="flex flex-col gap-2">
                {data.sections.map((s) => (
                  <li
                    key={s.chunk_id}
                    className="rounded-[2px] border border-line bg-surface2 px-3 py-2 text-xs text-ink"
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
              <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Shared Notes</p>
              <ul className="flex flex-col gap-2">
                {(data.notes || []).map((n) => (
                  <li key={n.resource_id} className="rounded-[2px] border border-line bg-surface2 p-3 text-xs">
                    <div className="flex items-center gap-1.5 font-medium text-ink">
                      <FileText className="h-3.5 w-3.5 text-accent-red" />
                      <span>{n.title}</span>
                      <span className="font-mono text-[10px] text-muted">· {n.author_role}</span>
                    </div>
                    <p className="mt-1 text-muted whitespace-pre-wrap">{truncate(n.content, 260)}</p>
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

      {/* Topic Quiz Preparation Modal */}
      <TopicQuizPrepModal
        open={prepModalOpen}
        onClose={() => setPrepModalOpen(false)}
        context={{
          topic,
          class_id: classId,
        }}
      />
    </div>
  );
}
