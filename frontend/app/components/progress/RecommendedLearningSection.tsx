"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Sparkles,
  Video,
  FileText,
  HelpCircle,
  PlayCircle,
  ExternalLink,
  BookOpen,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
} from "lucide-react";
import { Card, CardHeader } from "../ui/Card";
import { Badge, type BadgeTone } from "../ui/Badge";
import { Button, ButtonLink } from "../ui/Button";
import { Alert, EmptyState, Skeleton, SkeletonText } from "../ui/Feedback";
import { Modal } from "../ui/Modal";
import { VideoPlayerModal } from "../resources/VideoPlayerModal";
import { apiFetch, errorMessage } from "../../lib/api";
import { percent, plural } from "../../lib/format";
import type {
  ProgressRecommendationsResponse,
  ProgressRecommendationItem,
  RecommendationVideo,
  WeakTopicRecommendationGroup,
  InsufficientEvidenceTopic,
} from "../../lib/types";

interface RecommendedLearningSectionProps {
  classId: string;
}

export function RecommendedLearningSection({ classId }: RecommendedLearningSectionProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ProgressRecommendationsResponse | null>(null);

  // Modal states
  const [activeVideo, setActiveVideo] = useState<RecommendationVideo | null>(null);
  const [activeNote, setActiveNote] = useState<{ title: string; content: string; topic: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

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
    };
  }, [classId]);

  function handleAction(item: ProgressRecommendationItem, topicName: string) {
    if (item.action === "watch") {
      if (item.video_id) {
        setActiveVideo({
          title: item.title,
          video_id: item.video_id,
          channel: item.channel || "Educational Channel",
          url: item.url || `https://www.youtube.com/watch?v=${item.video_id}`,
          duration: item.duration,
          thumbnail: item.thumbnail,
          source: item.source === "faculty" ? "faculty" : item.source === "student_suggested" ? "student_suggested" : "auto",
        });
      } else if (item.url) {
        window.open(item.url, "_blank", "noopener,noreferrer");
      }
    } else if (item.action === "read") {
      setActiveNote({
        title: item.title,
        content: item.content_snippet || "No detailed notes text available.",
        topic: topicName,
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

  const insufficientList = data ? (data.insufficient_evidence_topics || data.insufficient_evidence || []) : [];
  const totalRecs = data?.total_recommended_resources ?? (data?.weak_topics.reduce((acc, g) => acc + (g.resources?.length || g.recommendations?.length || 0), 0) ?? 0);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader
          icon={<Sparkles className="h-5 w-5 text-accent-secondary" />}
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
        ) : !data || (data.weak_topics.length === 0 && insufficientList.length === 0) ? (
          <div className="mt-4">
            <EmptyState
              compact
              icon={<CheckCircle2 className="h-6 w-6 text-success" />}
              title="All Topics Strong!"
              description="You have achieved solid mastery (70%+) across all assessed curriculum topics. Keep reviewing or challenge yourself with practice quizzes."
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
                    const resources = group.resources || group.recommendations || [];
                    const scorePct = percent(group.mastery_score);
                    const isLow = group.mastery_band === "low" || group.mastery_score < 0.6;
                    const tone: BadgeTone = isLow ? "red" : "amber";

                    return (
                      <div
                        key={topicName}
                        className="rounded-xl border border-subtle bg-surface-muted/40 p-4 transition-colors hover:border-strong"
                      >
                        {/* Topic Header */}
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-subtle pb-3">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-primary">{topicName}</span>
                            <Badge tone={tone} dot>
                              {scorePct} Mastery
                            </Badge>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-tertiary">
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

                        {/* Topic Resources */}
                        <div className="mt-3 grid gap-3 sm:grid-cols-2">
                          {resources.map((item) => (
                            <div
                              key={item.id}
                              className="flex flex-col justify-between rounded-lg border border-subtle bg-surface p-3.5 shadow-sm transition hover:shadow-md"
                            >
                              <div className="flex flex-col gap-2">
                                <div className="flex items-center justify-between gap-2">
                                  <Badge tone={getBadgeTone(item)} dot={item.source === "faculty"}>
                                    {getBadgeLabel(item)}
                                  </Badge>
                                  {item.duration && (
                                    <span className="text-xs text-tertiary">{item.duration}</span>
                                  )}
                                </div>

                                <h4 className="line-clamp-2 text-sm font-medium text-primary">
                                  {item.title}
                                </h4>

                                {item.channel && (
                                  <p className="text-xs text-tertiary">{item.channel}</p>
                                )}

                                {item.content_snippet && (
                                  <p className="line-clamp-2 text-xs text-secondary">
                                    {item.content_snippet}
                                  </p>
                                )}
                              </div>

                              <div className="mt-3 flex items-center justify-end pt-2 border-t border-subtle/60">
                                {item.action === "practise" ? (
                                  <ButtonLink
                                    href={item.action_url || "/quiz"}
                                    variant="secondary"
                                    size="sm"
                                    icon={<HelpCircle className="h-3.5 w-3.5" />}
                                  >
                                    Practise Quiz
                                  </ButtonLink>
                                ) : item.action === "watch" ? (
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
                                    variant="secondary"
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
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Insufficient Evidence Section */}
            {insufficientList.length > 0 && (
              <div className="flex flex-col gap-3 rounded-xl border border-dashed border-subtle bg-surface-muted/30 p-4">
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-warning" />
                  <h3 className="text-sm font-semibold text-primary">
                    Diagnostic Assessment Needed
                  </h3>
                </div>
                <p className="text-xs text-secondary">
                  The following topics do not have enough quiz attempts yet to evaluate mastery accurately. Take a diagnostic quiz to identify your strengths and learning needs.
                </p>

                <div className="mt-2 grid gap-2 sm:grid-cols-2 md:grid-cols-3">
                  {insufficientList.map((t) => {
                    const topicName = t.topic || t.topic_name || "Curriculum Topic";
                    return (
                      <div
                        key={topicName}
                        className="flex items-center justify-between rounded-lg border border-subtle bg-surface p-3"
                      >
                        <div className="min-w-0 pr-2">
                          <p className="truncate text-xs font-medium text-primary">{topicName}</p>
                          <p className="text-[0.6875rem] text-tertiary">No quiz data yet</p>
                        </div>
                        <ButtonLink
                          href={t.action_url || "/quiz"}
                          variant="ghost"
                          size="sm"
                          className="shrink-0 text-xs"
                        >
                          Test <ArrowRight className="ml-1 h-3 w-3" />
                        </ButtonLink>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Video Player Modal */}
      <VideoPlayerModal video={activeVideo} onClose={() => setActiveVideo(null)} />

      {/* Note Reader Modal */}
      {activeNote && (
        <Modal
          open={Boolean(activeNote)}
          onClose={() => setActiveNote(null)}
          title={activeNote.title}
          description={`Faculty Study Note · ${activeNote.topic}`}
        >
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-2">
              <Badge tone="green" dot>
                Faculty Curated Material
              </Badge>
            </div>
            <div className="max-h-[60vh] overflow-y-auto rounded-lg bg-surface-muted/50 p-4 text-sm leading-relaxed text-primary whitespace-pre-wrap">
              {activeNote.content}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
