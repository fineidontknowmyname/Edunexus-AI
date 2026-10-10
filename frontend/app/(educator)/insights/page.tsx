"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  BarChart3,
  Brain,
  CalendarPlus,
  Flag,
  Flame,
  MessagesSquare,
  RefreshCw,
  Users,
} from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi, useAsync } from "../../lib/hooks/useApi";
import { useClassParam, useClasses } from "../../lib/hooks/useClasses";
import { formatDate, formatDateTime, formatRelative, percent, plural } from "../../lib/format";
import type {
  AtRiskStudent,
  ClassContextResponse,
  ClassInsightsResponse,
  ClassRow,
  FlaggedMessage,
  TrendingTopic,
} from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonCard, SkeletonText } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ProgressBar, StatCard, masteryTone } from "../../components/ui/Stat";
import { ClassPicker } from "../../components/layout/ClassPicker";
import { cn } from "../../lib/cn";

export default function InsightsPage() {
  return (
    <Suspense fallback={<PageContainer width="wide"><PageSkeleton /></PageContainer>}>
      <InsightsInner />
    </Suspense>
  );
}

function InsightsInner() {
  const classes = useClasses();
  const [classId, setClassId] = useClassParam(classes.data);

  if (classes.error) {
    return (
      <PageContainer width="wide">
        <PageHeader title="Class insights" />
        <ErrorState message={classes.error} onRetry={classes.reload} />
      </PageContainer>
    );
  }
  if (!classes.data) {
    return (
      <PageContainer width="wide">
        <PageSkeleton />
      </PageContainer>
    );
  }
  const activeClass = classes.data.find((c) => c.id === classId);

  return (
    <PageContainer width="wide">
      <PageHeader
        title="Class insights"
        description={activeClass ? `How ${activeClass.name} is doing, where they're stuck, and who needs help.` : "Mastery, misconceptions and at-risk students."}
        actions={<ClassPicker classes={classes.data} value={classId} onChange={setClassId} />}
      />
      {!activeClass ? (
        <EmptyState
          icon={<BarChart3 className="h-5 w-5" />}
          title="No classes yet"
          description="Create a class and upload material to start seeing insights."
          action={<Link href="/upload" className="text-sm font-medium text-accent-secondary hover:underline">Create a class</Link>}
        />
      ) : (
        <ClassInsights key={activeClass.id} activeClass={activeClass} />
      )}
    </PageContainer>
  );
}

interface InsightsBundle {
  insights: ClassInsightsResponse;
  atRisk: AtRiskStudent[];
  trending: TrendingTopic[];
  flags: FlaggedMessage[];
}

function ClassInsights({ activeClass }: { activeClass: ClassRow }) {
  const id = activeClass.id;
  const bundle = useAsync<InsightsBundle>(`insights:${id}`, async () => {
    const [insights, atRisk, trending, flags] = await Promise.all([
      apiFetch<ClassInsightsResponse>(`/insights/class/${id}`),
      apiFetch<AtRiskStudent[]>(`/insights/students/at-risk?class_id=${id}`),
      apiFetch<TrendingTopic[]>(`/insights/questions/trending?class_id=${id}`),
      apiFetch<FlaggedMessage[]>(`/insights/flags?class_id=${id}`),
    ]);
    return { insights, atRisk, trending, flags };
  });
  const context = useApi<ClassContextResponse>(`/context/class/${id}`);

  if (bundle.error && !bundle.data) return <ErrorState message={bundle.error} onRetry={bundle.reload} />;
  if (!bundle.data) {
    return (
      <div className="grid gap-6 lg:grid-cols-3" role="status">
        <span className="sr-only">Loading insights…</span>
        <SkeletonCard lines={8} className="lg:col-span-2" />
        <SkeletonCard lines={5} />
      </div>
    );
  }

  const { insights, atRisk, trending, flags } = bundle.data;
  const heat = [...insights.heatmap].sort((a, b) => a.average_mastery - b.average_mastery);
  const avg = heat.length ? heat.reduce((s, h) => s + h.average_mastery, 0) / heat.length : null;
  const struggling = heat.reduce((n, h) => n + h.struggling_count, 0);
  const upcoming = (context.data?.assessments ?? [])
    .filter((a) => new Date(a.date) >= new Date(new Date().toDateString()))
    .sort((a, b) => a.date.localeCompare(b.date));

  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Class mastery" value={avg === null ? "—" : percent(avg)} hint={plural(heat.length, "topic")} icon={<BarChart3 className="h-4 w-4" />} />
        <StatCard label="At risk" value={atRisk.length} hint={upcoming[0] ? `before ${upcoming[0].name}` : "no assessment scheduled"} icon={<AlertTriangle className="h-4 w-4" />} tone={atRisk.length ? "danger" : "default"} />
        <StatCard label="Struggling" value={struggling} hint="student-topic pairs below 40%" icon={<Users className="h-4 w-4" />} tone={struggling ? "warning" : "default"} />
        <StatCard label="Flagged replies" value={flags.length} hint="from students" icon={<Flag className="h-4 w-4" />} tone={flags.length ? "warning" : "default"} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader
              icon={<BarChart3 className="h-4 w-4" />}
              title="Mastery by topic"
              description="Average quiz mastery across the class, weakest first."
              actions={
                <div className="flex items-center gap-3 text-xs text-tertiary" aria-hidden>
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-danger" />&lt;40%</span>
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-warning" />40–69%</span>
                  <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-success" />70%+</span>
                </div>
              }
            />
            {heat.length === 0 ? (
              <EmptyState compact title="No quiz data yet" description="Once students take a quiz, topic mastery shows up here." />
            ) : (
              <ul className="flex flex-col divide-y divide-subtle">
                {heat.map((h) => (
                  <li key={h.topic} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 py-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto]">
                    <span className="truncate text-sm font-medium text-primary">{h.topic}</span>
                    <span className="flex items-center gap-2 justify-self-end sm:order-3">
                      {h.struggling_count > 0 && <Badge tone="red">{h.struggling_count} struggling</Badge>}
                      <span className={cn("w-10 text-right text-sm font-semibold tabular-nums", masteryTone(h.average_mastery) === "green" ? "text-success" : masteryTone(h.average_mastery) === "amber" ? "text-warning" : "text-danger")}>
                        {percent(h.average_mastery)}
                      </span>
                    </span>
                    <div className="col-span-2 flex items-center gap-3 sm:col-span-1">
                      <ProgressBar value={h.average_mastery} label={`${h.topic} class mastery`} className="h-2.5" />
                      <span className="w-16 shrink-0 text-xs text-tertiary">{plural(h.student_count, "student")}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader
              icon={<AlertTriangle className="h-4 w-4" />}
              title="At-risk students"
              description="Weak on topics covered by an upcoming assessment."
            />
            {atRisk.length === 0 ? (
              <EmptyState
                compact
                title={upcoming.length ? "No one is at risk" : "No assessment scheduled"}
                description={upcoming.length ? "Everyone is on track for the next assessment." : "Schedule an assessment to see who isn't ready for it."}
              />
            ) : (
              <ul className="flex flex-col divide-y divide-subtle">
                {[...atRisk]
                  .sort((a, b) => b.weak_topics_in_scope.length - a.weak_topics_in_scope.length)
                  .map((s) => (
                    <li key={s.student_id}>
                      <Link
                        href={`/students/${s.student_id}?class_id=${activeClass.id}&name=${encodeURIComponent(s.full_name)}`}
                        className="group flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-primary group-hover:text-accent-secondary">{s.full_name}</p>
                          <p className="truncate text-xs text-tertiary">{s.email}</p>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
                          {s.weak_topics_in_scope.slice(0, 3).map((t) => (
                            <Badge key={t} tone="amber">{t}</Badge>
                          ))}
                          {s.weak_topics_in_scope.length > 3 && <Badge>+{s.weak_topics_in_scope.length - 3}</Badge>}
                          <Badge tone={s.days_remaining <= 3 ? "red" : "gray"}>{s.days_remaining}d left</Badge>
                        </div>
                      </Link>
                    </li>
                  ))}
              </ul>
            )}
          </Card>

          <ConfusionCard activeClass={activeClass} entries={insights.class_confusion} onRefreshed={bundle.reload} />

          <Card>
            <CardHeader icon={<Brain className="h-4 w-4" />} title="Common misconceptions" description="Detected from wrong quiz answers." />
            {insights.misconceptions.length === 0 ? (
              <EmptyState compact title="None detected yet" description="Misconceptions appear once students answer quizzes." />
            ) : (
              <ul className="flex flex-col divide-y divide-subtle">
                {[...insights.misconceptions].sort((a, b) => b.count - a.count).map((m, i) => (
                  <li key={i} className="flex items-start justify-between gap-3 py-3">
                    <div className="min-w-0 text-sm">
                      <p className="font-medium text-primary">{m.topic}</p>
                      <p className="text-secondary">{m.description}</p>
                    </div>
                    <Badge tone="amber">{plural(m.count, "student")}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <ScheduleAssessmentCard
            activeClass={activeClass}
            topics={heat.map((h) => h.topic)}
            context={context.data}
            upcoming={upcoming}
            onSaved={() => {
              context.reload();
              bundle.reload();
            }}
          />

          <Card>
            <CardHeader icon={<Flame className="h-4 w-4" />} title="Trending topics" description="Most-asked in the last 7 days." />
            {trending.length === 0 ? (
              <p className="text-sm text-tertiary">No questions asked recently.</p>
            ) : (
              <ol className="flex flex-col gap-2">
                {trending.map((t, i) => (
                  <li key={t.topic} className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="w-4 text-xs tabular-nums text-tertiary">{i + 1}</span>
                      <span className="truncate text-primary">{t.topic}</span>
                    </span>
                    <span className="shrink-0 text-xs tabular-nums text-tertiary">{plural(t.questions_asked, "question")}</span>
                  </li>
                ))}
              </ol>
            )}
          </Card>

          <Card>
            <CardHeader icon={<Flag className="h-4 w-4" />} title="Flagged responses" description="Tutor answers students marked as wrong or unhelpful." />
            {flags.length === 0 ? (
              <p className="text-sm text-tertiary">No flagged responses.</p>
            ) : (
              <ul className="flex flex-col gap-3">
                {flags.map((f) => (
                  <li key={f.message_id} className="rounded-lg border border-subtle p-3">
                    <div className="flex items-center justify-between gap-2 text-xs text-tertiary">
                      <span className="truncate font-medium text-secondary">{f.student_name}</span>
                      <span className="shrink-0">{formatRelative(f.created_at)}</span>
                    </div>
                    <p className="mt-1.5 line-clamp-4 text-sm text-primary" title={formatDateTime(f.created_at)}>{f.content}</p>
                    {f.source_type && (
                      <Badge tone={f.source_type === "curriculum" ? "green" : "amber"} className="mt-2">
                        {f.source_type === "curriculum" ? "Curriculum" : "General knowledge"}
                      </Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

function ConfusionCard({
  activeClass,
  entries,
  onRefreshed,
}: {
  activeClass: ClassRow;
  entries: ClassInsightsResponse["class_confusion"];
  onRefreshed: () => void;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const subjectId = activeClass.subject_id;
  const computedAt = entries[0]?.computed_at;
  const total = entries.reduce((n, e) => n + e.cluster_size, 0);

  async function refresh() {
    if (!subjectId) return;
    setRefreshing(true);
    setError(null);
    try {
      await apiFetch(`/reflections/cluster?class_id=${activeClass.id}&subject_id=${subjectId}`, { method: "POST" });
      onRefreshed();
    } catch (err) {
      setError(errorMessage(err, "Couldn't refresh class confusion."));
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<MessagesSquare className="h-4 w-4" />}
        title="What the class finds confusing"
        description={computedAt ? `Grouped from student reflections · updated ${formatRelative(computedAt)}` : "Grouped from students' post-quiz reflections."}
        actions={
          <Button variant="secondary" size="sm" onClick={refresh} loading={refreshing} disabled={!subjectId} icon={<RefreshCw className="h-3.5 w-3.5" aria-hidden />}>
            Refresh
          </Button>
        }
      />
      {error && <Alert tone="danger" className="mb-3">{error}</Alert>}
      {!subjectId ? (
        <p className="text-sm text-tertiary">This class has no subject set, so reflections can&apos;t be grouped.</p>
      ) : entries.length === 0 ? (
        <EmptyState compact title="No themes yet" description="Refresh once a few students have shared reflections after quizzes." />
      ) : (
        <ul className="flex flex-col gap-2.5">
          {[...entries].sort((a, b) => b.cluster_size - a.cluster_size).map((c, i) => (
            <li key={i} className="relative overflow-hidden rounded-lg border border-subtle p-3">
              <span
                className="absolute inset-y-0 left-0 bg-accent-secondary/8"
                style={{ width: `${total ? Math.max(8, (c.cluster_size / total) * 100) : 0}%` }}
                aria-hidden
              />
              <div className="relative flex items-start justify-between gap-3">
                <p className="text-sm text-primary">&ldquo;{c.representative_text}&rdquo;</p>
                <Badge tone="blue" className="shrink-0">{plural(c.cluster_size, "student")}</Badge>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ScheduleAssessmentCard({
  activeClass,
  topics,
  context,
  upcoming,
  onSaved,
}: {
  activeClass: ClassRow;
  topics: string[];
  context: ClassContextResponse | null;
  upcoming: ClassContextResponse["assessments"];
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [extra, setExtra] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function toggle(topic: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const existing = context ?? (await apiFetch<ClassContextResponse>(`/context/class/${activeClass.id}`));
      const covers = [...selected, ...extra.split(",").map((s) => s.trim()).filter(Boolean)];
      await apiFetch(`/context/class/${activeClass.id}/assessments`, {
        method: "PATCH",
        body: { assessments: [...existing.assessments, { name: name.trim(), date, covers }] },
      });
      setSuccess(`${name.trim()} scheduled for ${formatDate(date)}.`);
      setName("");
      setDate("");
      setSelected(new Set());
      setExtra("");
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Couldn't schedule the assessment."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader icon={<CalendarPlus className="h-4 w-4" />} title="Assessments" description="Students weak on in-scope topics are flagged as at risk." />
      {upcoming.length > 0 ? (
        <ul className="mb-4 flex flex-col gap-2">
          {upcoming.map((a) => (
            <li key={`${a.name}-${a.date}`} className="rounded-lg border border-subtle bg-surface-muted/50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-primary">{a.name}</span>
                <span className="shrink-0 text-xs text-tertiary">{formatDate(a.date)}</span>
              </div>
              {a.covers.length > 0 && <p className="mt-1 line-clamp-2 text-xs text-tertiary">{a.covers.join(", ")}</p>}
            </li>
          ))}
        </ul>
      ) : context ? (
        <p className="mb-4 text-sm text-tertiary">No upcoming assessments.</p>
      ) : (
        <SkeletonText lines={2} className="mb-4" />
      )}
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 border-t border-subtle pt-4">
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Mid-term 1" />
        <Input label="Date" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        {topics.length > 0 && (
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium text-secondary">Topics covered</legend>
            <div className="flex flex-wrap gap-1.5">
              {topics.map((t) => {
                const on = selected.has(t);
                return (
                  <button
                    key={t}
                    type="button"
                    aria-pressed={on}
                    onClick={() => toggle(t)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-xs transition-colors",
                      on ? "border-accent-secondary bg-accent-secondary/12 font-medium text-accent-secondary" : "border-strong text-secondary hover:bg-surface-muted"
                    )}
                  >
                    {t}
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}
        <Input
          label={topics.length > 0 ? "Other topics (comma-separated)" : "Topics covered (comma-separated)"}
          value={extra}
          onChange={(e) => setExtra(e.target.value)}
          placeholder="SJF, Round Robin, FCFS"
        />
        {error && <Alert tone="danger">{error}</Alert>}
        {success && <Alert tone="success">{success}</Alert>}
        <Button type="submit" loading={saving} disabled={!name.trim() || !date}>
          Schedule assessment
        </Button>
      </form>
    </Card>
  );
}
