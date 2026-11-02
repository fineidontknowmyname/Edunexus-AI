"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Clock,
  ListChecks,
  Loader2,
  PlayCircle,
  RotateCcw,
  Target,
} from "lucide-react";
import { Modal } from "../ui/Modal";
import { Button, ButtonLink } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Alert } from "../ui/Feedback";
import { percent, plural } from "../../lib/format";
import { apiFetch, ApiError } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { VideoPlayerModal } from "../resources/VideoPlayerModal";
import type {
  RecommendationResponse,
  RecommendationVideo,
  TopicQuizPrepContext,
  TopicQuizResponse,
} from "../../lib/types";
import { RecommendationModeBanner } from "../progress/RecommendationModeBanner";

interface TopicQuizPrepModalProps {
  open: boolean;
  onClose: () => void;
  context: TopicQuizPrepContext | null;
  onLearnConcept?: () => void;
  onWatchVideo?: (video: RecommendationVideo) => void;
}

export function TopicQuizPrepModal({
  open,
  onClose,
  context,
  onLearnConcept,
  onWatchVideo,
}: TopicQuizPrepModalProps) {
  const router = useRouter();
  const [assessmentState, setAssessmentState] = useState<{
    key: string;
    isGenerating: boolean;
    error: string | null;
  }>({ key: "", isGenerating: false, error: null });
  const [videoState, setVideoState] = useState<{
    key: string;
    video: RecommendationVideo | null;
  }>({ key: "", video: null });
  const requestVersion = useRef(0);
  const modalKey = JSON.stringify([open, context?.topic, context?.class_id, context?.topic_id]);

  // Invalidate old requests; keyed state resets visibly on open/topic changes.
  useLayoutEffect(() => {
    requestVersion.current += 1;
  }, [open, context?.topic, context?.class_id, context?.topic_id]);

  const currentAssessmentState = assessmentState.key === modalKey
    ? assessmentState
    : { key: modalKey, isGenerating: false, error: null };
  const isGenerating = currentAssessmentState.isGenerating;
  const error = currentAssessmentState.error;
  const activeVideo = videoState.key === modalKey ? videoState.video : null;

  const recUrl =
    open && context?.class_id && context?.topic
      ? `/recommendations?class_id=${encodeURIComponent(context.class_id)}&topic=${encodeURIComponent(context.topic)}${
          context.topic_id ? `&topic_id=${encodeURIComponent(context.topic_id)}` : ""
        }`
      : null;
  const {
    data: recData,
    error: recommendationError,
    loading: recommendationsLoading,
  } = useApi<RecommendationResponse>(recUrl);

  if (!context) return null;

  const scorePct = context.mastery_score != null ? percent(context.mastery_score) : null;
  const isLow = context.mastery_score != null && context.mastery_score < 0.6;
  const attempts = context.attempts ?? 0;
  const videos = (recData?.videos || []).slice(0, 3);
  const documents = recData?.documents || [];
  const bodyHasFocusableChildren =
    videos.length > 0 || documents.some((document) => Boolean(document.file_url)) || Boolean(error);

  const handleStartAssessment = async () => {
    if (!context.class_id || !context.topic || isGenerating) return;
    const requestVersionAtStart = requestVersion.current;
    const requestedTopic = context.topic;
    setAssessmentState({ key: modalKey, isGenerating: true, error: null });

    try {
      const res = await apiFetch<TopicQuizResponse>("/quizzes/topic-quiz", {
        method: "POST",
        body: {
          class_id: context.class_id,
          topic: context.topic,
          topic_id: context.topic_id || undefined,
          num_questions: 5,
        },
      });

      if (requestVersion.current === requestVersionAtStart) {
        onClose();
        router.push(
          `/quiz/${res.quiz_id}?topic=${encodeURIComponent(requestedTopic)}&origin=recommendations`
        );
      }
    } catch (err: unknown) {
      if (requestVersion.current === requestVersionAtStart) {
        const message = err instanceof ApiError
          ? err.message || "Failed to generate topic assessment."
          : err instanceof Error
          ? err.message
          : "An unexpected error occurred while preparing your assessment.";
        setAssessmentState({ key: modalKey, isGenerating: false, error: message });
      }
    } finally {
      if (requestVersion.current === requestVersionAtStart) {
        setAssessmentState((current) =>
          current.key === modalKey
            ? { ...current, isGenerating: false }
            : current
        );
      }
    }
  };

  return (
    <>
      <Modal
        open={open}
        onClose={() => {
          if (!isGenerating) {
            setAssessmentState({ key: modalKey, isGenerating: false, error: null });
            onClose();
          }
        }}
        bracket="ASSESSMENT PREP"
        title="Topic Assessment Preparation"
        description="Calibrate your understanding with a targeted topic evaluation."
        scrollable
        bodyTabIndex={bodyHasFocusableChildren ? undefined : 0}
        footer={
          <>
            {onLearnConcept ? (
              <Button
                variant="outline"
                size="sm"
                icon={<BookOpen className="h-3.5 w-3.5" />}
                disabled={isGenerating}
                onClick={() => {
                  setAssessmentState({ key: modalKey, isGenerating: false, error: null });
                  onClose();
                  onLearnConcept();
                }}
              >
                Learn Concept
              </Button>
            ) : (
              <ButtonLink
                href="/path"
                variant="outline"
                size="sm"
                icon={<BookOpen className="h-3.5 w-3.5" />}
              >
                Learn Concept
              </ButtonLink>
            )}

            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setAssessmentState({ key: modalKey, isGenerating: false, error: null });
                  onClose();
                }}
                disabled={isGenerating}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={
                  isGenerating ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <PlayCircle className="h-3.5 w-3.5" />
                  )
                }
                disabled={isGenerating || !context.class_id || recData?.has_material === false}
                onClick={handleStartAssessment}
              >
                {isGenerating ? "Preparing…" : "Start Assessment →"}
              </Button>
            </div>
          </>
        }
      >
        <div className="flex flex-col gap-3 text-xs">
          {/* Topic Banner */}
          <div className="rounded-[2px] border border-line bg-surface2/60 p-3">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              {context.subject_name && (
                <Badge tone="gray">{context.subject_name}</Badge>
              )}
              {context.class_name && (
                <span className="font-mono text-[9px] uppercase tracking-wider text-muted">
                  {context.class_name}
                </span>
              )}
              {scorePct ? (
                <Badge tone={isLow ? "red" : "amber"} dot>
                  Est. {scorePct}
                </Badge>
              ) : (
                <Badge tone="gray">Diagnostic</Badge>
              )}
            </div>

            <h3 className="font-serif text-2xl text-ink flex items-center gap-2 leading-tight">
              <Target className="h-4 w-4 text-red shrink-0" aria-hidden="true" />
              <span>{context.topic}</span>
            </h3>

            <p className="mt-1.5 font-sans text-xs text-muted leading-relaxed">
              {attempts > 0
                ? `You have completed ${attempts} ${plural(attempts, "attempt")} on this topic. This assessment will re-evaluate your understanding.`
                : "No previous attempts logged. This assessment will establish your baseline mastery estimate."}
            </p>
          </div>

          {/* Specs */}
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="rounded-[2px] border border-line bg-surface p-3 flex flex-col justify-between">
              <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase text-muted">
                <ListChecks className="h-3 w-3 text-red" />
                <span>Format</span>
              </div>
              <p className="mt-1 font-serif text-lg text-ink">5 Diagnostic Items</p>
              <p className="font-mono text-[9px] text-muted">SC, MC &amp; True/False</p>
            </div>

            <div className="rounded-[2px] border border-line bg-surface p-3 flex flex-col justify-between">
              <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase text-muted">
                <Clock className="h-3 w-3 text-red" />
                <span>Pacing</span>
              </div>
              <p className="mt-1 font-serif text-lg text-ink">~8 Minutes</p>
              <p className="font-mono text-[9px] text-muted">Untimed practice mode</p>
            </div>
          </div>

          {recData && (
            <RecommendationModeBanner mode={recData.mode} reason={recData.reason} />
          )}

          <div className="rounded-[2px] border border-line bg-surface p-3">
            <h4 className="mb-2 font-mono text-[9px] uppercase tracking-wider text-muted font-semibold">
              Approved Class Videos
            </h4>
            {videos.length > 0 ? (
              <ul className="flex flex-col gap-2">
                {videos.map((video) => (
                  <li key={video.video_id} className="flex flex-col gap-1.5 border-b border-line/60 pb-2 last:border-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge tone={video.match_type === "exact" ? "green" : "amber"}>
                        {video.match_type === "exact" ? "Exact" : "Related"}
                      </Badge>
                      <span className="font-mono text-[10px] text-muted">{video.channel}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="font-serif text-sm text-ink font-medium">{video.title}</p>
                        {video.match_reason && (
                          <p className="mt-0.5 text-xs text-muted">{video.match_reason}</p>
                        )}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        icon={<PlayCircle className="h-3 w-3 text-red" />}
                        onClick={() => {
                          if (onWatchVideo) onWatchVideo(video);
                          else setVideoState({ key: modalKey, video });
                        }}
                      >
                        Watch
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted">
                {recommendationsLoading ? "Loading approved class videos…" : "No approved class videos found for this topic."}
              </p>
            )}
          </div>

          <div className="rounded-[2px] border border-line bg-surface p-3">
            <h4 className="mb-2 font-mono text-[9px] uppercase tracking-wider text-muted font-semibold">
              Approved Curriculum Documents
            </h4>
            {documents.length > 0 ? (
              <ul className="flex flex-col gap-2">
                {documents.map((document) => (
                  <li key={document.document_id} className="rounded-[2px] border border-line/60 bg-surface2 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <p className="font-serif text-sm text-ink">
                        {document.title}
                        {document.page_number != null ? ` · p.${document.page_number}` : ""}
                      </p>
                      {document.file_url && (
                        <ButtonLink href={document.file_url} variant="outline" size="sm">
                          Open
                        </ButtonLink>
                      )}
                    </div>
                    {document.content && (
                      <p className="mt-1 text-xs text-muted">{document.content}</p>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted">
                {recommendationsLoading ? "Loading approved curriculum documents…" : "No matching ready curriculum document was found."}
              </p>
            )}
            {recData?.sections?.length ? (
              <ul className="mt-2 flex flex-col gap-2">
                {recData.sections.map((section) => (
                  <li key={section.chunk_id} className="border-t border-line/60 pt-2 text-xs text-muted">
                    <span className="font-mono text-[10px] text-ink">
                      {section.document_name || "Course material"}
                      {section.page_number != null ? ` · p.${section.page_number}` : ""}
                      {section.section_heading ? ` · ${section.section_heading}` : ""}
                    </span>
                    <p className="mt-1 line-clamp-3">{section.text}</p>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          {recommendationError && (
            <Alert tone="danger">
              Recommendations could not be loaded. The assessment service will check for approved material before generation.
            </Alert>
          )}

          {recommendationsLoading ? (
            <div className="rounded-[2px] border border-line bg-surface2/40 p-3 font-mono text-[9px] uppercase tracking-wider text-muted">
              Checking approved curriculum material…
            </div>
          ) : recData?.has_material ? (
            <div className="rounded-[2px] border border-line bg-surface2/40 p-3 font-mono text-[9px] uppercase tracking-wider text-muted">
              Assessment grounded in {recData.chunk_count} approved curriculum {plural(recData.chunk_count, "section")} for <b>{context.topic}</b>.
            </div>
          ) : recData ? (
            <Alert tone="warning">
              No approved curriculum material is available for this topic yet. Start Assessment is disabled.
            </Alert>
          ) : (
            <div className="rounded-[2px] border border-line bg-surface2/40 p-3 font-mono text-[9px] uppercase tracking-wider text-muted">
              Grounding status is unavailable until recommendations load.
            </div>
          )}

          {/* Generation status / error */}
          {isGenerating ? (
            <div className="rounded-[2px] border border-line bg-surface2 p-4 flex items-center gap-3">
              <Loader2 className="h-4 w-4 animate-spin text-red shrink-0" />
              <div>
                <p className="font-mono text-xs uppercase tracking-wider text-ink font-semibold">Generating Assessment…</p>
                <p className="font-sans text-xs text-muted mt-0.5">
                  Preparing a topic-focused assessment for <b>{context.topic}</b>.
                </p>
              </div>
            </div>
          ) : error ? (
            <Alert tone="danger">
              <div className="flex flex-col gap-2 font-mono text-xs">
                <p>{error}</p>
                <div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleStartAssessment}
                    icon={<RotateCcw className="h-3 w-3" />}
                  >
                    Try Again
                  </Button>
                </div>
              </div>
            </Alert>
          ) : null}

        </div>
      </Modal>

      {/* Video Modal Player */}
      <VideoPlayerModal
        video={activeVideo}
        onClose={() => setVideoState({ key: modalKey, video: null })}
      />
    </>
  );
}
