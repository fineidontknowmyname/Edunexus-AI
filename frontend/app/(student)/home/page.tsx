"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  Compass,
  ListChecks,
  MessageSquare,
  Route,
} from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import { useAuth } from "../../lib/hooks/useAuth";
import { firstName, percent, plural } from "../../lib/format";
import type {
  AvailableQuiz,
  ClassRow,
  DashboardResponse,
  LearningPathEntry,
  LearningPathResponse,
  QuizAttemptSummary,
  RoutingMap,
} from "../../lib/types";
import { Button, ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui/Feedback";
import { PageContainer } from "../../components/ui/PageHeader";
import { KpiStrip, KpiCell, FocusRow, ProgressBar } from "../../components/ui/Stat";
import { ProgressRing } from "../../components/ui/DataVisualizations";
import { StudentClassGate } from "../../components/layout/StudentClassGate";
import { guidedSessionHref } from "../../components/progress/RecommendationPanel";
import { TopicQuizPrepModal } from "../../components/quiz/TopicQuizPrepModal";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function pickNext(path: LearningPathEntry[]): LearningPathEntry | null {
  if (path.length === 0) return null;
  return [...path].sort((a, b) => a.priority - b.priority || a.syllabus_index - b.syllabus_index)[0];
}

export default function StudentHomePage() {
  return (
    <StudentClassGate width="wide">
      {(activeClass, picker) => <StudentHome key={activeClass.id} activeClass={activeClass} picker={picker} />}
    </StudentClassGate>
  );
}

function StudentHome({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const { user } = useAuth();
  const [prepModalTopic, setPrepModalTopic] = useState<string | null>(null);
  const qs = `class_id=${activeClass.id}`;
  const dashboard = useApi<DashboardResponse>(`/progress/dashboard?${qs}`);
  const path = useApi<LearningPathResponse>(`/progress/path?${qs}`);
  const routing = useApi<RoutingMap>(`/progress/routing?${qs}`);
  const quizzes = useApi<AvailableQuiz[]>(`/quizzes/available?${qs}`);
  const attempts = useApi<QuizAttemptSummary[]>("/quizzes/attempts/mine");

  const givenName = firstName(user?.full_name);
  const d = dashboard.data;
  const avgMastery = d && d.mastery.length > 0 ? d.mastery.reduce((s, m) => s + m.score, 0) / d.mastery.length : null;
  const next = path.data ? pickNext(path.data.path) : null;
  const nextRouting = next ? routing.data?.[next.topic] : undefined;
  const interveneTopics = Object.entries(routing.data ?? {})
    .filter(([, label]) => label === "intervene")
    .map(([topic]) => topic);
  const lastScoreByQuiz = new Map<string, number>();
  for (const a of attempts.data ?? []) {
    if (!lastScoreByQuiz.has(a.quiz_id)) lastScoreByQuiz.set(a.quiz_id, a.score);
  }
  const weakest = d ? [...d.mastery].sort((a, b) => a.score - b.score).slice(0, 4) : [];

  return (
    <PageContainer width="wide">
      {/* Reference Welcome Hero Area */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between pb-7 mb-7 border-b border-line gap-4">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
            [ STUDENT / OVERVIEW ]
          </div>
          <h1 className="font-serif text-4xl sm:text-5xl lg:text-[64px] text-ink leading-[0.95] tracking-tight">
            {greeting()},<br />
            <em className="text-red font-normal">{givenName || "Student"}.</em>
          </h1>
          <p className="font-sans text-xs sm:text-sm text-muted mt-3 max-w-xl">
            A clear view of your subject progress, curriculum mastery and recommended next steps.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {picker("w-full sm:w-60")}
          <ButtonLink href="/chat" variant="primary" icon={<MessageSquare className="h-3.5 w-3.5" aria-hidden />}>
            Ask the tutor ↗
          </ButtonLink>
        </div>
      </div>

      {dashboard.error ? (
        <ErrorState message={dashboard.error} onRetry={dashboard.reload} />
      ) : !d ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 border-b border-line pb-6 gap-4" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-[2px]" />
          ))}
        </div>
      ) : (
        /* Reference 4-Column KPI Strip */
        <KpiStrip className="mb-8">
          <KpiCell
            label="Enrolled Class"
            value={activeClass.name.slice(0, 16)}
            caption={activeClass.subject || "Current semester"}
          />
          <KpiCell
            label="Average Mastery"
            value={avgMastery === null ? "—" : percent(avgMastery)}
            caption={`${plural(d.mastery.length, "topic")} assessed across syllabus`}
            tone={avgMastery !== null && avgMastery >= 0.7 ? "green" : undefined}
          />
          <KpiCell
            label="Learning Streak"
            value={`${String(d.engagement.current_streak).padStart(2, "0")}`}
            caption={`Best record: ${d.engagement.longest_streak} days`}
            tone={d.engagement.current_streak > 0 ? "red" : undefined}
          />
          <KpiCell
            label="Available Quizzes"
            value={quizzes.data ? `${String(quizzes.data.length).padStart(2, "0")}` : "—"}
            caption="Ready for practice & evaluation"
          />
        </KpiStrip>
      )}

      {/* Reference Two-Column Dashboard Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.35fr_0.8fr] gap-8">
        {/* Left Column: Recommended Focus & Available Quizzes */}
        <div className="flex flex-col gap-8">
          {/* Recommended Next Focus Panel */}
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ RECOMMENDED NEXT FOCUS ]
            </div>
            <h3 className="font-serif text-2xl sm:text-[29px] text-ink leading-tight mb-4">
              Continue where you left off.
            </h3>

            {path.error ? (
              <ErrorState message={path.error} onRetry={path.reload} />
            ) : !path.data ? (
              <div className="space-y-3">
                <Skeleton className="h-14 w-full" />
                <Skeleton className="h-14 w-full" />
              </div>
            ) : !next ? (
              <EmptyState
                compact
                bracket="RECOMMENDATIONS"
                icon={<Route className="h-5 w-5" />}
                title="No topics tracked yet"
                description="Once syllabus materials are approved, your personalized learning path will populate here."
              />
            ) : (
              <div className="border border-line bg-surface2/50 p-5 rounded-[2px] mt-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="dot" aria-hidden="true" />
                    <h4 className="font-serif text-2xl text-ink leading-snug">{next.topic}</h4>
                  </div>
                  <div className="flex items-center gap-2">
                    {next.in_assessment_scope && (
                      <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-red border border-red/40 px-2 py-0.5 rounded-[2px]">
                        In Exam Scope
                      </span>
                    )}
                    {nextRouting === "intervene" && (
                      <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-warning border border-warning/40 px-2 py-0.5 rounded-[2px]">
                        Guided Review
                      </span>
                    )}
                  </div>
                </div>

                <p className="font-sans text-xs text-muted mt-2 leading-relaxed">
                  {next.attempts === 0
                    ? "Initial diagnostic quiz needed to calibrate mastery on this topic."
                    : `Estimated: ${percent(next.mastery_score)} across ${plural(next.attempts, "attempt")}.`}
                </p>

                {next.attempts > 0 && (
                  <ProgressBar value={next.mastery_score} label={`${next.topic} estimated mastery`} className="mt-3 max-w-md" />
                )}

                <div className="mt-5 flex flex-wrap gap-2.5">
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<ListChecks className="h-3.5 w-3.5" aria-hidden />}
                    onClick={() => setPrepModalTopic(next.topic)}
                  >
                    Take a Test →
                  </Button>
                  <ButtonLink href="/progress" variant="outline" size="sm" icon={<BookOpen className="h-3.5 w-3.5" aria-hidden />}>
                    Learn the Concept ↗
                  </ButtonLink>
                  {nextRouting === "intervene" && (
                    <ButtonLink href={guidedSessionHref(next.topic)} variant="outline" size="sm" icon={<Compass className="h-3.5 w-3.5" aria-hidden />}>
                      Tutor Session ↗
                    </ButtonLink>
                  )}
                </div>
              </div>
            )}

            {interveneTopics.filter((t) => t !== next?.topic).length > 0 && (
              <div className="mt-4 pt-3 border-t border-line font-mono text-[9px] uppercase tracking-[0.08em] flex flex-wrap items-center gap-2 text-muted">
                <span>Other flagged topics:</span>
                {interveneTopics
                  .filter((t) => t !== next?.topic)
                  .map((t) => (
                    <Link
                      key={t}
                      href={guidedSessionHref(t)}
                      className="border border-line px-2 py-0.5 text-ink hover:border-red hover:text-red transition-colors"
                    >
                      {t} ↗
                    </Link>
                  ))}
              </div>
            )}
          </div>

          {/* Assigned & Practice Quizzes Panel */}
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ ASSIGNED & PRACTICE QUIZZES ]
            </div>
            <h3 className="font-serif text-2xl sm:text-[29px] text-ink leading-tight mb-2">
              Curriculum evaluations
            </h3>

            {quizzes.error ? (
              <ErrorState message={quizzes.error} onRetry={quizzes.reload} />
            ) : !quizzes.data ? (
              <div className="space-y-3 mt-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : quizzes.data.length === 0 ? (
              <EmptyState compact bracket="QUIZZES" title="No quizzes yet" description="Your faculty has not published quizzes for this class yet." />
            ) : (
              <div className="divide-y divide-line mt-4">
                {quizzes.data.slice(0, 5).map((q, idx) => {
                  const last = lastScoreByQuiz.get(q.id);
                  return (
                    <FocusRow
                      key={q.id}
                      icon={String(idx + 1).padStart(2, "0")}
                      title={q.title}
                      description={[
                        q.unit != null && `Unit ${q.unit}`,
                        q.chapter != null && `Chapter ${q.chapter}`,
                        plural(q.question_count, "question"),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                      actions={
                        <div className="flex items-center gap-3">
                          {last !== undefined ? (
                            <span className="font-mono text-[10px] text-muted">
                              Last: <b className="text-ink">{Math.round(last)}%</b>
                            </span>
                          ) : (
                            <span className="font-mono text-[9px] text-red uppercase tracking-wider">
                              [ New ]
                            </span>
                          )}
                          <ButtonLink href={`/quiz/${q.id}`} variant="outline" size="sm">
                            Open →
                          </ButtonLink>
                        </div>
                      }
                    />
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Telemetry & Weakest Topics Rail */}
        <div className="flex flex-col gap-8">
          {/* Study Telemetry Panel with Progress Ring */}
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ STUDY TELEMETRY ]
            </div>
            <h3 className="font-serif text-2xl text-ink leading-tight mb-4">
              Overall mastery
            </h3>

            <div className="flex items-center gap-6 py-2">
              <ProgressRing
                value={avgMastery ?? 0}
                size={116}
                strokeWidth={9}
              />
              <div className="font-sans text-xs text-muted leading-relaxed">
                <p className="font-medium text-ink mb-1">
                  {avgMastery === null
                    ? "Initial evaluation pending."
                    : avgMastery >= 0.75
                    ? "Mastery steady across syllabus."
                    : "Focus on diagnostic weak topics."}
                </p>
                <p>
                  Calculated across {d?.mastery.length ?? 0} syllabus topics grounded in verified faculty material.
                </p>
              </div>
            </div>
          </div>

          {/* Topics Needing Review Panel */}
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ REVIEW QUEUE ]
            </div>
            <h3 className="font-serif text-2xl text-ink leading-tight mb-4">
              Topics to review
            </h3>

            {!d ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : weakest.length === 0 ? (
              <EmptyState compact bracket="MASTERY" title="No telemetry yet" description="Complete a quiz to initialize topic score tracking." />
            ) : (
              <div className="divide-y divide-line">
                {weakest.map((m) => (
                  <div key={m.topic} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.08em] mb-1.5">
                      <span className="text-ink truncate max-w-[70%] font-medium">{m.topic}</span>
                      <span className="text-muted tabular-nums">Est. {percent(m.score)}</span>
                    </div>
                    <ProgressBar value={m.score} label={`${m.topic} estimated mastery`} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Upcoming Assessment Alert Box (if scheduled) */}
          {d?.upcoming_focus && (
            <div className="bg-surface2 border border-line p-6 rounded-[2px]">
              <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-1">
                [ UPCOMING ASSESSMENT ]
              </div>
              <h4 className="font-serif text-2xl text-ink leading-snug">
                {d.upcoming_focus.assessment_name}
              </h4>
              <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted mt-1">
                IN {plural(d.upcoming_focus.days_remaining, "DAY")} · {plural(d.upcoming_focus.topics_in_scope.length, "TOPIC")} IN SCOPE
              </p>
              {d.upcoming_focus.weak_topics_in_scope.length > 0 ? (
                <div className="mt-4 pt-3 border-t border-line">
                  <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-red block mb-2">
                    Review priority:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {d.upcoming_focus.weak_topics_in_scope.map((t) => (
                      <span key={t} className="font-mono text-[9px] uppercase border border-red/40 px-2 py-0.5 text-red bg-surface">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="font-mono text-[9px] uppercase tracking-wider text-green mt-3">
                  All topics in scope currently above threshold.
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      <TopicQuizPrepModal
        open={Boolean(prepModalTopic)}
        onClose={() => setPrepModalTopic(null)}
        context={prepModalTopic ? {
          topic: prepModalTopic,
          mastery_score: next?.topic === prepModalTopic ? next?.mastery_score : null,
          attempts: next?.topic === prepModalTopic ? next?.attempts : 0,
          class_id: activeClass.id,
          class_name: activeClass.name,
        } : null}
      />
    </PageContainer>
  );
}
