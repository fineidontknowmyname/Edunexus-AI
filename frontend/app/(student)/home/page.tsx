"use client";

import Link from "next/link";
import {
  ArrowRight,
  CalendarClock,
  Compass,
  Flame,
  ListChecks,
  MessageSquare,
  Route,
  Target,
  TrendingUp,
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
import { Card, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorState, Skeleton, SkeletonCard, SkeletonText } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ProgressBar, StatCard } from "../../components/ui/Stat";
import { StudentClassGate } from "../../components/layout/StudentClassGate";
import { guidedSessionHref } from "../../components/progress/RecommendationPanel";

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
  return <StudentClassGate width="wide">{(activeClass, picker) => <StudentHome key={activeClass.id} activeClass={activeClass} picker={picker} />}</StudentClassGate>;
}

function StudentHome({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const { user } = useAuth();
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
      <PageHeader
        eyebrow={activeClass.name}
        title={givenName ? `${greeting()}, ${givenName}` : greeting()}
        description="Here's where you stand and what to focus on next."
        actions={
          <>
            {picker()}
            <ButtonLink href="/chat" variant="primary" icon={<MessageSquare className="h-4 w-4" aria-hidden />}>
              Ask the tutor
            </ButtonLink>
          </>
        }
      />

      {dashboard.error ? (
        <ErrorState message={dashboard.error} onRetry={dashboard.reload} />
      ) : !d ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[6.5rem] rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Avg mastery"
            value={avgMastery === null ? "—" : percent(avgMastery)}
            hint={plural(d.mastery.length, "topic") + " tracked"}
            icon={<TrendingUp className="h-4 w-4" />}
            href="/progress"
          />
          <StatCard
            label="Day streak"
            value={d.engagement.current_streak}
            hint={`Best: ${d.engagement.longest_streak}`}
            icon={<Flame className="h-4 w-4" />}
            tone={d.engagement.current_streak > 0 ? "success" : "default"}
          />
          <StatCard
            label="Next assessment"
            value={d.upcoming_focus ? `${d.upcoming_focus.days_remaining}d` : "—"}
            hint={d.upcoming_focus ? d.upcoming_focus.assessment_name : "Nothing scheduled"}
            icon={<CalendarClock className="h-4 w-4" />}
            tone={d.upcoming_focus && d.upcoming_focus.days_remaining <= 7 ? "warning" : "default"}
          />
          <StatCard
            label="Quizzes"
            value={quizzes.data ? quizzes.data.length : "—"}
            hint="available to take"
            icon={<ListChecks className="h-4 w-4" />}
            href="/quiz"
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader
              icon={<Target className="h-4 w-4" />}
              title="Recommended next"
              description="Based on your mastery, the syllabus and upcoming assessments."
              actions={
                <Link href="/path" className="inline-flex items-center gap-1 text-sm font-medium text-accent-secondary hover:underline">
                  Full path <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Link>
              }
            />
            {path.error ? (
              <ErrorState message={path.error} onRetry={path.reload} />
            ) : !path.data ? (
              <SkeletonText lines={3} />
            ) : !next ? (
              <EmptyState
                compact
                icon={<Route className="h-5 w-5" />}
                title="No topics tracked yet"
                description="Once your teacher uploads course material, your personalised path will appear here."
              />
            ) : (
              <div className="rounded-xl border border-subtle bg-surface-muted/50 p-4 sm:p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-lg font-semibold text-primary">{next.topic}</h3>
                  {next.in_assessment_scope && <Badge tone="red" dot>In exam scope</Badge>}
                  {nextRouting === "intervene" && <Badge tone="amber" dot>Needs a guided session</Badge>}
                </div>
                <p className="mt-1 text-sm text-tertiary">
                  {next.attempts === 0
                    ? "You haven't attempted this topic yet."
                    : `${percent(next.mastery_score)} mastery across ${plural(next.attempts, "attempt")}.`}
                </p>
                {next.attempts > 0 && <ProgressBar value={next.mastery_score} label={`${next.topic} mastery`} className="mt-3 max-w-sm" />}
                <div className="mt-4 flex flex-wrap gap-2">
                  {nextRouting === "intervene" ? (
                    <ButtonLink href={guidedSessionHref(next.topic)} variant="accent" icon={<Compass className="h-4 w-4" aria-hidden />}>
                      Work through it together
                    </ButtonLink>
                  ) : next.attempts === 0 ? (
                    <ButtonLink href="/quiz" variant="accent" icon={<ListChecks className="h-4 w-4" aria-hidden />}>
                      Take a quiz
                    </ButtonLink>
                  ) : (
                    <ButtonLink href={guidedSessionHref(next.topic)} variant="accent" icon={<Compass className="h-4 w-4" aria-hidden />}>
                      Practise with the tutor
                    </ButtonLink>
                  )}
                  <ButtonLink href="/path" variant="secondary">
                    See resources
                  </ButtonLink>
                </div>
              </div>
            )}
            {interveneTopics.filter((t) => t !== next?.topic).length > 0 && (
              <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                <span className="text-tertiary">Also flagged for a guided session:</span>
                {interveneTopics
                  .filter((t) => t !== next?.topic)
                  .map((t) => (
                    <Link
                      key={t}
                      href={guidedSessionHref(t)}
                      className="rounded-full border border-warning/40 bg-warning/10 px-2.5 py-0.5 text-xs font-medium text-warning hover:bg-warning/15"
                    >
                      {t}
                    </Link>
                  ))}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader
              icon={<ListChecks className="h-4 w-4" />}
              title="Available quizzes"
              actions={
                <Link href="/quiz" className="inline-flex items-center gap-1 text-sm font-medium text-accent-secondary hover:underline">
                  All quizzes <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                </Link>
              }
            />
            {quizzes.error ? (
              <ErrorState message={quizzes.error} onRetry={quizzes.reload} />
            ) : !quizzes.data ? (
              <SkeletonText lines={3} />
            ) : quizzes.data.length === 0 ? (
              <EmptyState compact title="No quizzes yet" description="Your teacher hasn't published a quiz for this class yet." />
            ) : (
              <ul className="flex flex-col divide-y divide-subtle">
                {quizzes.data.slice(0, 4).map((q) => {
                  const last = lastScoreByQuiz.get(q.id);
                  return (
                    <li key={q.id}>
                      <Link href={`/quiz/${q.id}`} className="group flex items-center justify-between gap-3 rounded-md py-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-primary group-hover:text-accent-secondary">{q.title}</p>
                          <p className="text-xs text-tertiary">
                            {[q.unit != null && `Unit ${q.unit}`, q.chapter != null && `Chapter ${q.chapter}`, plural(q.question_count, "question")]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        </div>
                        {last !== undefined ? (
                          <Badge tone={last >= 70 ? "green" : last >= 40 ? "amber" : "red"}>Last: {Math.round(last)}%</Badge>
                        ) : (
                          <Badge tone="blue">New</Badge>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          {d?.upcoming_focus ? (
            <Card className="border-warning/35">
              <CardHeader icon={<CalendarClock className="h-4 w-4" />} title="Upcoming assessment" />
              <p className="text-base font-semibold text-primary">{d.upcoming_focus.assessment_name}</p>
              <p className="text-sm text-tertiary">
                in {plural(d.upcoming_focus.days_remaining, "day")} · {plural(d.upcoming_focus.topics_in_scope.length, "topic")} in scope
              </p>
              {d.upcoming_focus.weak_topics_in_scope.length > 0 ? (
                <div className="mt-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-warning">Review these first</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.upcoming_focus.weak_topics_in_scope.map((t) => (
                      <Badge key={t} tone="amber">{t}</Badge>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-sm text-success">You&apos;re in good shape on every topic in scope.</p>
              )}
            </Card>
          ) : !d && !dashboard.error ? (
            <SkeletonCard />
          ) : null}

          <Card>
            <CardHeader
              icon={<TrendingUp className="h-4 w-4" />}
              title="Weakest topics"
              actions={
                <Link href="/progress" className="text-sm font-medium text-accent-secondary hover:underline">
                  Progress
                </Link>
              }
            />
            {!d ? (
              <SkeletonText lines={4} />
            ) : weakest.length === 0 ? (
              <EmptyState compact title="Nothing to show yet" description="Take a quiz to see your mastery by topic." />
            ) : (
              <ul className="flex flex-col gap-4">
                {weakest.map((m) => (
                  <li key={m.topic}>
                    <div className="mb-1.5 flex items-baseline justify-between gap-2 text-sm">
                      <span className="truncate text-primary">{m.topic}</span>
                      <span className="font-semibold tabular-nums text-primary">{percent(m.score)}</span>
                    </div>
                    <ProgressBar value={m.score} label={`${m.topic} mastery`} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </PageContainer>
  );
}
