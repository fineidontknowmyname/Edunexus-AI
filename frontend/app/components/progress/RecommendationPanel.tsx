"use client";

import { useState } from "react";
import {
  FileText,
  ListChecks,
  Plus,
} from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import type { RecommendationResponse, RecommendationVideo } from "../../lib/types";
import { getRecommendationPresentation } from "../../lib/recommendationPresentation";
import { Button, ButtonLink } from "../ui/Button";
import { Alert, ErrorState, SkeletonText } from "../ui/Feedback";
import { VideoResourceCard } from "../resources/VideoResourceCard";
import { VideoPlayerModal } from "../resources/VideoPlayerModal";
import { StudentSuggestVideoModal } from "../resources/StudentSuggestVideoModal";
import { TopicQuizPrepModal } from "../quiz/TopicQuizPrepModal";
import { RecommendationModeBanner } from "./RecommendationModeBanner";

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

export function guidedSessionHref(topic: string): string {
  return `/chat?topic=${encodeURIComponent(topic)}&mode=socratic`;
}

export function RecommendationPanel({
  classId,
  topic,
  topicId,
}: {
  classId: string;
  topic: string;
  topicId?: string | null;
}) {
  const query = new URLSearchParams({ topic, class_id: classId });
  if (topicId) query.set("topic_id", topicId);
  const rec = useApi<RecommendationResponse>(`/recommendations?${query.toString()}`);
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
  const presentation = getRecommendationPresentation(data.mode, data.reason);
  const hasNotes = (data.notes || []).length > 0;
  const hasVideos = (data.videos || []).length > 0;
  const hasSections = (data.sections || []).length > 0;
  const documents = data.documents || [];
  const hasDocuments = documents.length > 0;

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

      {data.has_material ? (
        <Alert tone="success">
          Grounded in {data.chunk_count} approved curriculum {data.chunk_count === 1 ? "section" : "sections"}.
        </Alert>
      ) : (
        <Alert tone="warning">No approved curriculum material was found for this topic.</Alert>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <RecommendationModeBanner mode={data.mode} reason={data.reason} />
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Button
            variant="primary"
            size="sm"
            icon={<ListChecks className="h-3.5 w-3.5" />}
            onClick={() => setPrepModalOpen(true)}
          >
            {presentation.primaryCta}
          </Button>
          {data.mode === "ai_session" || data.mode === "diagnostic" || data.mode === "verification" ? (
            <ButtonLink href={guidedSessionHref(topic)} variant="outline" size="sm">
              {presentation.secondaryCta}
            </ButtonLink>
          ) : data.mode === "advance" ? (
            <a href="#recommended-resources" className="text-xs font-medium text-ink underline underline-offset-4">
              {presentation.secondaryCta}
            </a>
          ) : (
            <ButtonLink href="/progress" variant="outline" size="sm">
              {presentation.secondaryCta}
            </ButtonLink>
          )}
        </div>
      </div>

      {/* Resource Sections Header */}
      <div id="recommended-resources" className="flex flex-wrap items-center justify-between gap-2 pb-2">
        <h4 className="font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
          Recommended Learning Resources
        </h4>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setSuggestOpen(true)}
            icon={<Plus className="h-3 w-3" />}
          >
            Suggest video
          </Button>
        </div>
      </div>

      {!hasSections && !hasDocuments && !hasVideos && !hasNotes ? (
        <p className="py-2 font-mono text-xs text-muted">
          No approved class resources logged for this topic yet. You can suggest a helpful YouTube video or ask the tutor.
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
                    <p className="mb-1 font-mono text-[10px] text-muted">
                      {s.document_name || "Course curriculum"}
                      {s.page_number != null ? ` · p.${s.page_number}` : ""}
                      {s.section_heading ? ` · ${s.section_heading}` : ""}
                    </p>
                    {truncate(s.text, 240)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {hasDocuments && (
            <div>
              <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Approved course documents</p>
              <ul className="flex flex-col gap-2">
                {documents.map((document) => (
                  <li key={document.document_id} className="flex items-center justify-between gap-3 rounded-[2px] border border-line bg-surface2 px-3 py-2 text-xs">
                    <span className="text-ink">
                      {document.title}
                      {document.page_number != null ? ` · p.${document.page_number}` : ""}
                    </span>
                    {document.file_url && (
                      <ButtonLink href={document.file_url} variant="outline" size="sm">
                        Open
                      </ButtonLink>
                    )}
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
          topic_id: topicId,
          class_id: classId,
        }}
      />
    </div>
  );
}
