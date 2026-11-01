"use client";

import { FormEvent, Suspense, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { BarChart3, Brain, Flame, MessageSquareText, NotebookPen, Route, StickyNote, Trophy } from "lucide-react";
import { apiFetch, errorMessage } from "../../../lib/api";
import { ENGAGEMENT_INACTIVE_DAYS } from "../../../lib/constants";
import { useApi } from "../../../lib/hooks/useApi";
import { formatDateTime, formatRelative, percent, plural } from "../../../lib/format";
import type { MasteryTrend, StudentFullContext } from "../../../lib/types";
import { Card, CardHeader } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Textarea } from "../../../components/ui/Input";
import { Alert, EmptyState, ErrorState, PageSkeleton } from "../../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../../components/ui/PageHeader";
import { ProgressBar, StatCard } from "../../../components/ui/Stat";
import { MasteryBar } from "../../../components/progress/MasteryBar";
import { Avatar } from "../../../components/layout/UserMenu";

const TRENDS: MasteryTrend[] = ["improving", "stable", "declining", "not_started"];

export default function StudentDetailPage() {
  return (
    <Suspense fallback={<PageContainer><PageSkeleton /></PageContainer>}>
      <StudentDetail />
    </Suspense>
  );
}

function StudentDetail() {
  const params = useParams<{ studentId: string }>();
  const searchParams = useSearchParams();
  const classId = searchParams.get("class_id") ?? "";
  const name = searchParams.get("name") ?? "";
  const back = { href: classId ? `/insights?class_id=${classId}` : "/insights", label: "Class insights" };
  const query = useApi<StudentFullContext>(classId ? `/progress/student/${params.studentId}?class_id=${classId}` : null);

  if (!classId) {
    return (
      <PageContainer>
        <PageHeader title="Student" back={back} />
        <EmptyState title="Pick a class first" description="Open a student from the Class insights page so we know which class to show." />
      </PageContainer>
    );
  }
  if (query.error && !query.data) {
    return (
      <PageContainer>
        <PageHeader title={name || "Student"} back={back} />
        <ErrorState message={query.error} onRetry={query.reload} />
      </PageContainer>
    );
  }
  if (!query.data) {
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  }

  const { context, notes, learning_path } = query.data;
  const masteryEntries = Object.entries(context.mastery).sort((a, b) => a[1].score - b[1].score);
  const avg = masteryEntries.length ? masteryEntries.reduce((s, [, m]) => s + m.score, 0) / masteryEntries.length : null;
  const questions = Object.entries(context.interaction_patterns).sort((a, b) => b[1].questions_asked - a[1].questions_asked);

  return (
    <PageContainer>
      <PageHeader
        back={back}
        eyebrow="[ STUDENT PROFILE ]"
        title={
          <span className="flex items-center gap-3">
            <Avatar name={name || "Student"} className="h-10 w-10 text-sm" />
            <span className="font-serif">{name || "Student detail"}</span>
          </span>
        }
        description={
          (context.engagement.last_interaction_date || context.engagement.last_interaction)
            ? `Last active ${formatRelative(context.engagement.last_interaction_date || context.engagement.last_interaction || "")}`
            : "No activity recorded yet"
        }
        actions={context.engagement.is_inactive ? <Badge tone="amber" dot>Inactive ({ENGAGEMENT_INACTIVE_DAYS}+ days)</Badge> : undefined}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Avg mastery" value={avg === null ? "—" : percent(avg)} icon={<BarChart3 className="h-4 w-4" />} hint={plural(masteryEntries.length, "topic")} />
        <StatCard label="Streak" value={context.engagement.current_streak} icon={<Flame className="h-4 w-4" />} hint="days" />
        <StatCard label="Weak topics" value={context.weak_topics.length} icon={<Route className="h-4 w-4" />} tone={context.weak_topics.length ? "warning" : "default"} hint={context.weak_topics.slice(0, 2).join(", ") || "none"} />
        <StatCard label="Misconceptions" value={context.misconceptions.length} icon={<Brain className="h-4 w-4" />} tone={context.misconceptions.length ? "danger" : "default"} hint="unresolved" />
      </div>

      {context.upcoming_focus && (
        <Alert tone={context.upcoming_focus.weak_topics_in_scope.length ? "warning" : "info"} title={`${context.upcoming_focus.assessment_name} in ${plural(context.upcoming_focus.days_remaining, "day")}`}>
          {context.upcoming_focus.weak_topics_in_scope.length
            ? `Weak on ${context.upcoming_focus.weak_topics_in_scope.join(", ")}, which ${context.upcoming_focus.weak_topics_in_scope.length === 1 ? "is" : "are"} in scope.`
            : "On track for every topic in scope."}
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
        <div className="flex min-w-0 flex-col gap-6 lg:col-span-2">
          {context.misconceptions.length > 0 && (
            <Card>
              <CardHeader icon={<Brain className="h-4 w-4" />} title="Active misconceptions" description="Related quiz questions are hidden until the student works through these." />
              <ul className="flex flex-col gap-2">
                {context.misconceptions.map((m, i) => (
                  <li key={i} className="rounded-[2px] border border-line bg-surface2 px-3 py-2 text-sm">
                    <span className="font-serif text-[15px] text-ink">{m.topic}</span>
                    <span className="text-muted text-xs">: {m.description}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHeader icon={<BarChart3 className="h-4 w-4" />} title="Mastery by topic" description="Weakest first." />
            {masteryEntries.length === 0 ? (
              <EmptyState compact title="No quiz attempts yet" />
            ) : (
              <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
                {masteryEntries.map(([topic, m]) => (
                  <MasteryBar
                    key={topic}
                    topic={topic}
                    score={m.score}
                    trend={(TRENDS as string[]).includes(m.trend) ? (m.trend as MasteryTrend) : "stable"}
                    attempts={m.attempts}
                  />
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader icon={<Route className="h-4 w-4" />} title="Learning path" description="What the student sees as their priorities." />
            {learning_path.length === 0 ? (
              <p className="font-mono text-xs text-muted uppercase tracking-[0.06em]">No path yet.</p>
            ) : (
              <ol className="flex flex-col divide-y divide-line">
                {learning_path.map((entry, i) => (
                  <li key={entry.topic} className="grid grid-cols-[1.5rem_minmax(0,1fr)_6rem_3rem] items-center gap-3 py-2.5 text-sm">
                    <span className="font-mono text-xs tabular-nums text-muted">{String(i + 1).padStart(2, "0")}</span>
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-serif text-[15px] text-ink">{entry.topic}</span>
                      {entry.in_assessment_scope && <Badge tone="red" className="hidden sm:inline-flex">Exam</Badge>}
                    </span>
                    <ProgressBar value={entry.mastery_score} label={`${entry.topic} mastery`} />
                    <span className="text-right font-mono text-xs tabular-nums text-muted">{entry.attempts ? percent(entry.mastery_score) : "—"}</span>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <NotesCard studentId={params.studentId} classId={classId} notes={notes} onAdded={query.reload} />

          <Card>
            <CardHeader icon={<MessageSquareText className="h-4 w-4" />} title="Tutor questions" description="Topics this student asks about." />
            {questions.length === 0 ? (
              <p className="text-sm text-tertiary">No questions asked yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {questions.slice(0, 8).map(([topic, p]) => (
                  <li key={topic} className="flex items-center justify-between gap-2 text-sm">
                    <span className="truncate text-primary">{topic}</span>
                    <span className="shrink-0 text-xs text-tertiary">
                      {plural(p.questions_asked, "question")}
                      {p.last_asked ? ` · ${formatRelative(p.last_asked)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {context.strong_topics.length > 0 && (
            <Card>
              <CardHeader icon={<Trophy className="h-4 w-4" />} title="Strong topics" />
              <div className="flex flex-wrap gap-1.5">
                {context.strong_topics.map((t) => (
                  <Badge key={t} tone="green">{t}</Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {query.data.attempts && query.data.attempts.length > 0 && (
        <Card className="mt-6">
          <CardHeader icon={<Trophy className="h-4 w-4" />} title="Quiz attempts" description="Recent assessment attempts in this class." />
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-subtle text-xs text-muted">
                <tr>
                  <th className="py-2">Quiz</th>
                  <th className="py-2">Score</th>
                  <th className="py-2">Date</th>
                  <th className="py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-subtle">
                {query.data.attempts.map((att) => (
                  <tr key={att.id}>
                    <td className="py-2.5 font-medium">{att.quiz_title}</td>
                    <td className="py-2.5">{att.score !== null ? `${Math.round(att.score)}%` : "—"}</td>
                    <td className="py-2.5 text-xs text-muted">{att.completed_at ? formatRelative(att.completed_at) : (att.started_at ? formatRelative(att.started_at) : "—")}</td>
                    <td className="py-2.5 text-right">
                      <Badge tone={att.completed ? "green" : "gray"}>
                        {att.completed ? "Completed" : "In Progress"}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </PageContainer>
  );
}

function NotesCard({
  studentId,
  classId,
  notes,
  onAdded,
}: {
  studentId: string;
  classId: string;
  notes: StudentFullContext["notes"];
  onAdded: () => void;
}) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch("/context/notes", { method: "POST", body: { student_id: studentId, class_id: classId, note: text.trim() } });
      setText("");
      onAdded();
    } catch (err) {
      setError(errorMessage(err, "Couldn't save the note."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader icon={<NotebookPen className="h-4 w-4" />} title="Educator notes" description="The tutor uses your latest note to tailor its help." />
      <form onSubmit={handleAdd} className="flex flex-col gap-2">
        <Textarea
          label="New note"
          srOnlyLabel
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Struggles with deadlock conditions; use the dining philosophers example."
          rows={3}
          maxLength={2000}
        />
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" variant="secondary" loading={saving} disabled={!text.trim()} className="self-start" icon={<StickyNote className="h-4 w-4" aria-hidden />}>
          Add note
        </Button>
      </form>
      {notes.length > 0 && (
        <ul className="mt-4 flex flex-col gap-3 border-t border-subtle pt-4">
          {notes.map((n) => (
            <li key={n.id} className="text-sm">
              <p className="whitespace-pre-wrap text-primary">{n.note}</p>
              <p className="mt-0.5 text-xs text-tertiary">{formatDateTime(n.created_at)}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
