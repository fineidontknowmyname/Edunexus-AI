"use client";

import { useEffect, useState } from "react";
import {
  Sparkles,
  PlayCircle,
  ExternalLink,
  BookOpen,
  CheckCircle2,
  ArrowRight,
  ListChecks,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Card, CardHeader, CardTakeaway } from "../ui/Card";
import { Badge, type BadgeTone } from "../ui/Badge";
import { Button, ButtonLink } from "../ui/Button";
import { Alert, EmptyState, Skeleton } from "../ui/Feedback";
import { Modal } from "../ui/Modal";
import { VideoPlayerModal } from "../resources/VideoPlayerModal";
import { TopicQuizPrepModal } from "../quiz/TopicQuizPrepModal";
import { RecommendationModeBanner } from "./RecommendationModeBanner";
import { apiFetch, errorMessage, rawFetch } from "../../lib/api";
import { percent, plural } from "../../lib/format";
import {
  getProgressRecommendationMode,
  getRecommendationPresentation,
} from "../../lib/recommendationPresentation";
import type {
  ProgressRecommendationsResponse,
  ProgressRecommendationItem,
  RecommendationVideo,
  TopicQuizPrepContext,
} from "../../lib/types";

interface RecommendedLearningSectionProps {
  classId: string;
}

export function RecommendedLearningSection({ classId }: RecommendedLearningSectionProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ProgressRecommendationsResponse | null>(null);

  // Expanded topic state for "Learn the Concept"
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null);

  // Preparation modal state for "Take a Test"
  const [prepContext, setPrepContext] = useState<TopicQuizPrepContext | null>(null);

  // Resource viewer modal states
  const [activeVideo, setActiveVideo] = useState<RecommendationVideo | null>(null);
  const [activeNote, setActiveNote] = useState<{
    title: string;
    content: string;
    topic: string;
    document_id?: string | null;
    file_url?: string | null;
    downloading?: boolean;
    downloadError?: string | null;
  } | null>(null);

  function extractYouTubeId(url: string): string | null {
    const match = url.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([a-zA-Z0-9_-]{11})/);
    return match ? match[1] : null;
  }

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
    }, 0);

    apiFetch<ProgressRecommendationsResponse>(`/progress/recommendations?class_id=${classId}`)
      .then((res) => {
        if (cancelled) return;
        setData(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(errorMessage(err, "Failed to load personalized recommendations."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [classId]);

  function handleAction(item: ProgressRecommendationItem, topicName: string) {
    if (item.action === "watch") {
      const vid = item.video_id || (item.url ? extractYouTubeId(item.url) : null);
      if (vid) {
        setActiveVideo({
          title: item.title,
          video_id: vid,
          channel: item.channel || "Educational Channel",
          url: item.url || `https://www.youtube.com/watch?v=${vid}`,
          duration: item.duration || undefined,
          thumbnail: item.thumbnail || undefined,
          source: item.source === "faculty" ? "faculty" : item.source === "student_suggested" ? "student_suggested" : null,
        });
      } else if (item.url) {
        window.open(item.url, "_blank", "noopener,noreferrer");
      }
    } else if (item.action === "read") {
      setActiveNote({
        title: item.title,
        content: item.content || item.content_snippet || "No detailed notes text available.",
        topic: topicName,
        document_id: item.document_id,
        file_url: item.file_url,
      });
    }
  }

  function getBadgeLabel(item: ProgressRecommendationItem): string {
    if (item.badge_label) return item.badge_label;
    if (item.source === "faculty") return "Faculty Approved";
    if (item.source === "student_suggested") return "Student Suggested";
    if (item.source === "system") return "Practice Quiz";
    return "Related Tutorial";
  }

  function getBadgeTone(item: ProgressRecommendationItem): BadgeTone {
    if (item.source === "faculty") return "green";
    if (item.source === "student_suggested") return "blue";
    if (item.source === "system") return "info";
    return "gray";
  }

  const developingList = data?.developing_topics || [];
  const insufficientList = data ? (data.insufficient_evidence_topics || data.insufficient_evidence || []) : [];
  const totalRecs = data?.total_recommended_resources ?? ([...(data?.weak_topics || []), ...developingList].reduce((acc, g) => acc + (g.resources?.length || g.recommendations?.length || 0), 0) ?? 0);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader
          icon={<Sparkles className="h-5 w-5 text-accent-red" />}
          title="Personalised Learning Recommendations"
          description="Tailored resources dynamically recommended based on your quiz & assessment performance in this subject."
        />

        {loading ? (
          <div className="mt-4 flex flex-col gap-4">
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
          </div>
        ) : error ? (
          <div className="mt-4">
            <Alert tone="danger">{error}</Alert>
          </div>
        ) : !data || (data.weak_topics.length === 0 && developingList.length === 0 && insufficientList.length === 0) ? (
          <div className="mt-4">
            <EmptyState
              compact
              icon={<CheckCircle2 className="h-6 w-6 text-success" />}
              title="Topics Tracking Strongly"
              description="All assessed curriculum topics are currently estimated at 70%+ mastery. Continue reviewing or challenge yourself with practice quizzes."
              action={
                <ButtonLink href="/quiz" variant="secondary" size="sm">
                  Practice Advanced Quiz
                </ButtonLink>
              }
            />
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-6">
            {/* Weak Topics Section */}
            {data.weak_topics.length > 0 && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-primary">
                    Focus Areas ({data.weak_topics.length} {plural(data.weak_topics.length, "topic")} need reinforcement)
                  </h3>
                  <span className="text-xs text-tertiary">
                    {totalRecs} {plural(totalRecs, "resource")} curated
                  </span>
                </div>

                <div className="flex flex-col gap-4">
                  {data.weak_topics.map((group) => {
                    const topicName = group.topic || group.topic_name || "Focus Topic";
                    // Filter out synthetic quiz items from learning resources
                    const rawResources = group.resources || group.recommendations || [];
                    const learningResources = rawResources.filter((r) => r.resource_type !== "quiz");
                    const scorePct = percent(group.mastery_score);
                    const isLow = group.mastery_band === "low" || group.mastery_score < 0.6;
                    const tone: BadgeTone = isLow ? "red" : "amber";
                    const isExpanded = expandedTopic === topicName;
                    const mode = getProgressRecommendationMode(
                      group.attempts,
                      group.evidence_state,
                      group.mastery_band,
                    );
                    const presentation = getRecommendationPresentation(mode);

                    return (
                      <div
                        key={topicName}
                        className="rounded-[2px] border border-line bg-surface p-5 sm:p-6 transition-all duration-200 hover:border-ink shadow-xs"
                      >
                        {/* Topic Header & Metadata */}
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
                          <div>
                            <div className="flex items-center gap-2.5">
                              <span className="font-serif text-[18px] text-ink">{topicName}</span>
                              <Badge tone={tone} dot>
                                Est. {scorePct}
                              </Badge>
                            </div>
                            <div className="mt-2">
                              <RecommendationModeBanner mode={mode} />
                            </div>
                          </div>

                          <div className="flex items-center gap-3 font-mono text-xs text-muted uppercase tracking-[0.04em]">
                            <span>
                              {group.attempts} {plural(group.attempts, "attempt")}
                            </span>
                            {group.accuracy !== undefined && (
                              <>
                                <span>·</span>
                                <span>{percent(group.accuracy)} accuracy</span>
                              </>
                            )}
                          </div>
                        </div>

                        {/* Dual Action Decision Bar */}
                        <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2.5">
                          <p className="font-mono text-xs text-muted uppercase tracking-[0.06em]">
                            Choose an action to improve your mastery:
                          </p>

                          <div className="flex flex-wrap items-center gap-2">
                            {/* Action 1: Take a Test */}
                            <Button
                              variant="primary"
                              size="sm"
                              icon={<ListChecks className="h-3.5 w-3.5" />}
                              onClick={() =>
                                setPrepContext({
                                  topic: topicName,
                                  topic_id: group.topic_id,
                                  mastery_score: group.mastery_score,
                                  attempts: group.attempts,
                                  subject_name: data.subject_name,
                                  class_name: data.class_name,
                                  class_id: classId,
                                })
                              }
                            >
                              {presentation.primaryCta}
                            </Button>

                            {/* Action 2: Learn the Concept */}
                            {mode === "ai_session" && (
                              <>
                                <ButtonLink
                                  href={`/chat?topic=${encodeURIComponent(topicName)}&mode=socratic`}
                                  variant="outline"
                                  size="sm"
                                >
                                  {presentation.secondaryCta}
                                </ButtonLink>
                                <Button
                                  variant={isExpanded ? "primary" : "outline"}
                                  size="sm"
                                  icon={<BookOpen className="h-3.5 w-3.5" />}
                                  aria-expanded={isExpanded}
                                  onClick={() => setExpandedTopic(isExpanded ? null : topicName)}
                                >
                                  Learn Concept
                                  {isExpanded ? (
                                    <ChevronUp className="ml-1 h-3.5 w-3.5" />
                                  ) : (
                                    <ChevronDown className="ml-1 h-3.5 w-3.5" />
                                  )}
                                </Button>
                              </>
                            )}
                            {mode !== "ai_session" && (
                              <Button
                                variant={isExpanded ? "primary" : "outline"}
                                size="sm"
                                icon={<BookOpen className="h-3.5 w-3.5" />}
                                aria-expanded={isExpanded}
                                onClick={() => setExpandedTopic(isExpanded ? null : topicName)}
                              >
                                {presentation.secondaryCta}
                                {isExpanded ? (
                                  <ChevronUp className="ml-1 h-3.5 w-3.5" />
                                ) : (
                                  <ChevronDown className="ml-1 h-3.5 w-3.5" />
                                )}
                              </Button>
                            )}
                          </div>
                        </div>

                        {/* Expandable Resource Drawer ("Learn the Concept") */}
                        {isExpanded && (
                          <div className="mt-4 pt-4 border-t border-line">
                            <div className="mb-3 flex items-center justify-between">
                              <h4 className="font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                                Curated Learning Materials for {topicName}
                              </h4>
                              <span className="font-mono text-[11px] text-muted uppercase tracking-[0.04em]">
                                {learningResources.length} {plural(learningResources.length, "item")}
                              </span>
                            </div>

                            {learningResources.length === 0 ? (
                              <div className="rounded-[2px] border border-dashed border-line bg-surface2 p-4 text-center">
                                <p className="text-xs text-muted">
                                  No uploaded videos or notes found for this topic yet.
                                </p>
                                <ButtonLink
                                  href={`/chat?topic=${encodeURIComponent(topicName)}&mode=socratic`}
                                  variant="outline"
                                  size="sm"
                                  className="mt-2 text-xs"
                                >
                                  Ask AI Tutor in Socratic Mode
                                </ButtonLink>
                              </div>
                            ) : (
                              <div className="grid gap-3 sm:grid-cols-2">
                                {learningResources.map((item) => (
                                  <div
                                    key={item.id}
                                    className="flex flex-col justify-between rounded-[2px] border border-line bg-surface p-4 shadow-xs transition-all duration-200 hover:border-ink"
                                  >
                                    <div className="flex flex-col gap-2">
                                      <div className="flex items-center justify-between gap-2">
                                        <div className="flex items-center gap-1.5">
                                          <Badge tone={getBadgeTone(item)} dot={item.source === "faculty"}>
                                            {getBadgeLabel(item)}
                                          </Badge>
                                          {item.match_type && (
                                            <Badge tone={item.match_type === "exact" ? "green" : "amber"}>
                                              {item.match_type === "exact" ? "Exact" : "Related"}
                                            </Badge>
                                          )}
                                        </div>
                                        {item.duration && (
                                          <span className="font-mono text-xs text-muted">{item.duration}</span>
                                        )}
                                      </div>

                                      <h5 className="line-clamp-2 font-serif text-[15px] text-ink">
                                        {item.title}
                                      </h5>
                                      {item.match_reason && (
                                        <p className="text-xs text-muted">{item.match_reason}</p>
                                      )}

                                      {item.channel && (
                                        <p className="font-mono text-xs text-muted">{item.channel}</p>
                                      )}

                                      {item.content_snippet && (
                                        <p className="line-clamp-2 text-xs text-muted">
                                          {item.content_snippet}
                                        </p>
                                      )}
                                    </div>

                                    <div className="mt-3 flex items-center justify-end pt-2 border-t border-line">
                                      {item.action === "watch" ? (
                                        <Button
                                          variant="primary"
                                          size="sm"
                                          icon={<PlayCircle className="h-3.5 w-3.5" />}
                                          onClick={() => handleAction(item, topicName)}
                                        >
                                          Watch Video
                                        </Button>
                                      ) : (
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          icon={<BookOpen className="h-3.5 w-3.5" />}
                                          onClick={() => handleAction(item, topicName)}
                                        >
                                          Read Notes
                                        </Button>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Developing Topics Section (Almost there: 60-69%) */}
            {developingList.length > 0 && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-primary">
                    Almost there (60-69%) ({developingList.length} {plural(developingList.length, "topic")} close to mastery)
                  </h3>
                </div>

                <div className="flex flex-col gap-4">
                  {developingList.map((group) => {
                    const topicName = group.topic || group.topic_name || "Developing Topic";
                    const rawResources = group.resources || group.recommendations || [];
                    const learningResources = rawResources.filter((r) => r.resource_type !== "quiz");
                    const scorePct = percent(group.mastery_score);
                    const tone: BadgeTone = "amber";
                    const isExpanded = expandedTopic === topicName;
                    const mode = getProgressRecommendationMode(
                      group.attempts,
                      group.evidence_state,
                      group.mastery_band,
                    );
                    const presentation = getRecommendationPresentation(mode);

                    return (
                      <div
                        key={topicName}
                        className="rounded-xl border border-line bg-surface p-4 transition-all"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                          <div className="flex flex-col gap-2">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-primary text-base">
                                {topicName}
                              </span>
                              <Badge tone={tone}>
                                {scorePct}
                              </Badge>
                            </div>
                            <span className="text-xs text-tertiary">
                              {group.attempts} {plural(group.attempts, "attempt")}
                            </span>
                            <RecommendationModeBanner mode={mode} />
                          </div>

                          <div className="flex items-center gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              icon={<CheckCircle2 className="h-4 w-4" />}
                              onClick={() => setPrepContext({ topic: topicName, topic_id: group.topic_id, class_id: data.class_id })}
                            >
                              {presentation.primaryCta}
                            </Button>
                            {learningResources.length > 0 && (
                              <Button
                                variant="ghost"
                                size="sm"
                                icon={isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                                onClick={() => setExpandedTopic(isExpanded ? null : topicName)}
                              >
                                {isExpanded ? "Hide Resources" : `${presentation.secondaryCta} (${learningResources.length})`}
                              </Button>
                            )}
                          </div>
                        </div>

                        {/* Expanded resources */}
                        {isExpanded && learningResources.length > 0 && (
                          <div className="mt-4 pt-4 border-t border-line flex flex-col gap-3">
                            <div className="grid gap-3 sm:grid-cols-2">
                              {learningResources.map((item, idx) => (
                                <div key={item.id || idx} className="rounded-lg border border-line bg-surface2 p-3 flex flex-col justify-between">
                                  <div>
                                    <span className="text-xs font-semibold text-secondary">{item.title}</span>
                                    {item.match_reason && <p className="mt-1 text-xs text-muted">{item.match_reason}</p>}
                                    {item.channel && <p className="font-mono text-xs text-muted">{item.channel}</p>}
                                  </div>
                                  <div className="mt-3 flex justify-end">
                                    <Button
                                      variant="primary"
                                      size="sm"
                                      icon={item.action === "watch" ? <PlayCircle className="h-3.5 w-3.5" /> : <BookOpen className="h-3.5 w-3.5" />}
                                      onClick={() => handleAction(item, topicName)}
                                    >
                                      {item.action === "watch" ? "Watch Video" : "Read Notes"}
                                    </Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Insufficient Evidence Section */}
            {insufficientList.length > 0 && (
              <div className="flex flex-col gap-3 rounded-[2px] border border-dashed border-line bg-surface2 p-4">
                <RecommendationModeBanner
                  mode="initial_assessment"
                  reason="These topics do not have enough current assessment evidence. Take an initial assessment to establish your baseline."
                />

                <div className="mt-2 grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                  {insufficientList.map((t) => {
                    const topicName = t.topic || t.topic_name || "Curriculum Topic";
                    const presentation = getRecommendationPresentation("initial_assessment");
                    return (
                      <div
                        key={topicName}
                        className="flex items-center justify-between rounded-[2px] border border-line bg-surface p-3"
                      >
                        <div className="min-w-0 pr-2">
                          <p className="truncate font-serif text-sm text-ink">{topicName}</p>
                          <p className="font-mono text-[10px] uppercase tracking-[0.04em] text-muted">No quiz data yet</p>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="shrink-0"
                          onClick={() =>
                            setPrepContext({
                              topic: topicName,
                              topic_id: t.topic_id,
                              mastery_score: null,
                              attempts: 0,
                              subject_name: data.subject_name,
                              class_name: data.class_name,
                              class_id: classId,
                            })
                          }
                        >
                          {presentation.primaryCta} <ArrowRight className="ml-1 h-3 w-3" />
                        </Button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {data && data.weak_topics.length > 0 && (
              <CardTakeaway
                text={`${data.weak_topics.length} ${plural(data.weak_topics.length, "topic")} currently estimated below 70% threshold. Choose "Take a Test" or "Learn Concept" on any focus area above.`}
              />
            )}
          </div>
        )}
      </Card>

      {/* Topic Quiz Preparation Modal */}
      <TopicQuizPrepModal
        open={Boolean(prepContext)}
        onClose={() => setPrepContext(null)}
        context={prepContext}
        onLearnConcept={() => {
          if (prepContext) {
            setExpandedTopic(prepContext.topic);
          }
        }}
        onWatchVideo={(v) => setActiveVideo(v)}
      />

      {/* Video Player Modal */}
      <VideoPlayerModal video={activeVideo} onClose={() => setActiveVideo(null)} />

      {/* Note & Course Document Reader Modal */}
      {activeNote && (
        <Modal
          open={Boolean(activeNote)}
          onClose={() => setActiveNote(null)}
          title={activeNote.title}
          description={`Faculty Study Material · ${activeNote.topic}`}
        >
          <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Badge tone="green" dot>
                {activeNote.document_id ? "Faculty Course Document" : "Faculty Curated Notes"}
              </Badge>
              {activeNote.document_id && (
                <Button
                  size="sm"
                  variant="primary"
                  icon={<ExternalLink className="h-3.5 w-3.5" />}
                  onClick={async () => {
                    if (activeNote.downloading) return;
                    setActiveNote((prev) => (prev ? { ...prev, downloading: true, downloadError: null } : null));
                    try {
                      const res = await rawFetch(`/documents/${activeNote.document_id}/file`, {});
                      if (!res.ok) throw new Error("Could not download document file.");
                      const blob = await res.blob();
                      const blobUrl = URL.createObjectURL(blob);
                      window.open(blobUrl, "_blank", "noopener,noreferrer");
                      setActiveNote((prev) => (prev ? { ...prev, downloading: false } : null));
                    } catch {
                      setActiveNote((prev) =>
                        prev
                          ? {
                              ...prev,
                              downloading: false,
                              downloadError: "Unable to open document directly. Please try again or download via syllabus.",
                            }
                          : null
                      );
                    }
                  }}
                >
                  {activeNote.downloading ? "Opening Document…" : "View Original Document"}
                </Button>
              )}
            </div>

            {activeNote.downloadError && (
              <p className="text-xs text-danger">{activeNote.downloadError}</p>
            )}

            {activeNote.content && (
              <div className="max-h-[60vh] overflow-y-auto rounded-lg bg-surface-muted/50 p-4 text-sm leading-relaxed text-primary whitespace-pre-wrap">
                {activeNote.content}
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
