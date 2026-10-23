"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  ClipboardCheck,
  FileText,
  FileUp,
  School,
  Users,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { useAsync } from "../../lib/hooks/useApi";
import { useAuth } from "../../lib/hooks/useAuth";
import { useClasses } from "../../lib/hooks/useClasses";
import { firstName, formatRelative, percent, plural } from "../../lib/format";
import type { AtRiskStudent, ClassInsightsResponse, ClassRow, DocumentRow, PendingQuiz } from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorState, PageSkeleton, Skeleton, SkeletonText } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ProgressBar, StatCard } from "../../components/ui/Stat";
import { DocumentStatusBadge } from "../../components/educator/DocumentStatusBadge";

interface ClassSummary {
  cls: ClassRow;
  documents: DocumentRow[];
  pending: PendingQuiz[];
  atRisk: AtRiskStudent[];
  insights: ClassInsightsResponse | null;
}

async function loadSummaries(classes: ClassRow[]): Promise<ClassSummary[]> {
  return Promise.all(
    classes.map(async (cls) => {
      const [documents, pending, atRisk, insights] = await Promise.all([
        apiFetch<DocumentRow[]>(`/documents/?class_id=${cls.id}`).catch(() => [] as DocumentRow[]),
        apiFetch<PendingQuiz[]>(`/quizzes/pending?class_id=${cls.id}`).catch(() => [] as PendingQuiz[]),
        apiFetch<AtRiskStudent[]>(`/insights/students/at-risk?class_id=${cls.id}`).catch(() => [] as AtRiskStudent[]),
        apiFetch<ClassInsightsResponse>(`/insights/class/${cls.id}`).catch(() => null),
      ]);
      return { cls, documents, pending, atRisk, insights };
    })
  );
}

function classAverage(insights: ClassInsightsResponse | null): number | null {
  const rows = insights?.heatmap ?? [];
  if (rows.length === 0) return null;
  return rows.reduce((s, h) => s + h.average_mastery, 0) / rows.length;
}

export default function OverviewPage() {
  const { user } = useAuth();
  const classes = useClasses();
  const classKey = classes.data ? classes.data.map((c) => c.id).join(",") : null;
  const summaries = useAsync<ClassSummary[]>(classKey === null ? null : `overview:${classKey}`, () =>
    loadSummaries(classes.data ?? [])
  );

  if (classes.error) {
    return (
      <PageContainer width="wide">
        <PageHeader title="Overview" />
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

  const givenName = firstName(user?.full_name);

  if (classes.data.length === 0) {
    return (
      <PageContainer width="wide">
        <PageHeader title={givenName ? `Welcome, ${givenName}` : "Welcome"} description="Let's set up your first class." />
        <EmptyState
          icon={<School className="h-5 w-5" />}
          title="You don't have any classes yet"
          description="Create a class and upload your first chapter. Students can then join and start learning with the tutor."
          action={<ButtonLink href="/upload" variant="primary">Create a class</ButtonLink>}
        />
      </PageContainer>
    );
  }

  const data = summaries.data;
  const pendingQuizzes = data?.flatMap((s) => s.pending.map((q) => ({ quiz: q, cls: s.cls }))) ?? [];
  const pendingQuestions = pendingQuizzes.reduce(
    (n, { quiz }) => n + quiz.questions.filter((q) => q.status === "pending_review").length,
    0
  );
  const atRisk = data?.flatMap((s) => s.atRisk.map((st) => ({ student: st, cls: s.cls }))) ?? [];
  atRisk.sort((a, b) => b.student.weak_topics_in_scope.length - a.student.weak_topics_in_scope.length);
  const uniqueAtRisk = new Set(atRisk.map((a) => a.student.student_id)).size;
  const recentDocs = (data?.flatMap((s) => s.documents.map((d) => ({ doc: d, cls: s.cls }))) ?? [])
    .sort((a, b) => b.doc.created_at.localeCompare(a.doc.created_at))
    .slice(0, 5);
  const totalDocs = data?.reduce((n, s) => n + s.documents.length, 0) ?? 0;
  const processing = data?.reduce((n, s) => n + s.documents.filter((d) => d.status === "processing" || d.status === "pending").length, 0) ?? 0;

  return (
    <PageContainer width="wide">
      <PageHeader
        title={givenName ? `Welcome back, ${givenName}` : "Overview"}
        description="Your classes at a glance: what needs review and who needs attention."
        actions={
          <>
            <ButtonLink href="/upload" variant="secondary" icon={<FileUp className="h-4 w-4" aria-hidden />}>
              Upload material
            </ButtonLink>
            <ButtonLink href="/quiz-review" variant="primary" icon={<ClipboardCheck className="h-4 w-4" aria-hidden />}>
              Generate quiz
            </ButtonLink>
          </>
        }
      />

      {summaries.error && <ErrorState message={summaries.error} onRetry={summaries.reload} />}

      {!data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[6.5rem] rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Classes" value={classes.data.length} icon={<School className="h-4 w-4" />} hint={plural(totalDocs, "document")} />
          <StatCard
            label="Awaiting review"
            value={pendingQuestions}
            icon={<ClipboardCheck className="h-4 w-4" />}
            hint={`${plural(pendingQuizzes.length, "quiz", "quizzes")} pending`}
            tone={pendingQuestions > 0 ? "warning" : "default"}
            href="/quiz-review"
          />
          <StatCard
            label="At-risk students"
            value={uniqueAtRisk}
            icon={<AlertTriangle className="h-4 w-4" />}
            hint="before the next assessment"
            tone={uniqueAtRisk > 0 ? "danger" : "default"}
            href="/insights"
          />
          <StatCard
            label="Processing"
            value={processing}
            icon={<FileText className="h-4 w-4" />}
            hint={processing > 0 ? "documents indexing" : "all documents ready"}
            href="/upload"
          />
        </div>
      )}

      <section aria-labelledby="classes-heading" className="flex flex-col gap-3">
        <h2 id="classes-heading" className="text-base font-semibold text-primary">Your classes</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {classes.data.map((cls) => {
            const s = data?.find((x) => x.cls.id === cls.id);
            const avg = s ? classAverage(s.insights) : null;
            return (
              <Card key={cls.id} className="flex flex-col">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold text-primary">{cls.name}</h3>
                    <p className="truncate text-sm text-tertiary">
                      {[cls.subject, cls.semester ? `Semester ${cls.semester}` : null].filter(Boolean).join(" · ") || "No subject set"}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">{s && s.atRisk.length > 0 && <Badge tone="red" dot>{s.atRisk.length} at risk</Badge>}{cls.join_code && <Badge tone="blue" className="font-mono text-[0.6875rem]">Code: {cls.join_code}</Badge>}</div>
                </div>
                {!s ? (
                  <SkeletonText lines={2} className="mt-4" />
                ) : (
                  <>
                    <div className="mt-4">
                      <div className="mb-1.5 flex items-baseline justify-between text-sm">
                        <span className="text-secondary">Class mastery</span>
                        <span className="font-semibold tabular-nums text-primary">{avg === null ? "No data" : percent(avg)}</span>
                      </div>
                      <ProgressBar value={avg ?? 0} label={`${cls.name} average mastery`} />
                    </div>
                    <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
                      {[
                        { label: "Documents", value: s.documents.length },
                        { label: "To review", value: s.pending.reduce((n, q) => n + q.questions.filter((x) => x.status === "pending_review").length, 0) },
                        { label: "Topics", value: s.insights?.heatmap.length ?? 0 },
                      ].map((item) => (
                        <div key={item.label} className="rounded-lg bg-surface-muted/70 px-2 py-2">
                          <dt className="text-[0.6875rem] text-tertiary">{item.label}</dt>
                          <dd className="text-sm font-semibold tabular-nums text-primary">{item.value}</dd>
                        </div>
                      ))}
                    </dl>
                  </>
                )}
                <div className="mt-auto flex flex-wrap gap-2 pt-4">
                  <ButtonLink href={`/insights?class_id=${cls.id}`} variant="secondary" size="sm" icon={<BarChart3 className="h-3.5 w-3.5" aria-hidden />}>
                    Insights
                  </ButtonLink>
                  <ButtonLink href={`/upload?class_id=${cls.id}`} variant="ghost" size="sm">
                    Materials
                  </ButtonLink>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            icon={<Users className="h-4 w-4" />}
            title="Students who need attention"
            description="Weak on topics in an upcoming assessment."
            actions={<Link href="/insights" className="text-sm font-medium text-accent-secondary hover:underline">All insights</Link>}
          />
          {!data ? (
            <SkeletonText lines={4} />
          ) : atRisk.length === 0 ? (
            <EmptyState compact title="No one is flagged right now" description="Schedule an assessment in Class insights to track readiness." />
          ) : (
            <ul className="flex flex-col divide-y divide-subtle">
              {atRisk.slice(0, 6).map(({ student, cls }) => (
                <li key={`${cls.id}-${student.student_id}`}>
                  <Link
                    href={`/students/${student.student_id}?class_id=${cls.id}&name=${encodeURIComponent(student.full_name)}`}
                    className="group flex items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-primary group-hover:text-accent-secondary">{student.full_name}</p>
                      <p className="truncate text-xs text-tertiary">
                        {cls.name} · weak on {student.weak_topics_in_scope.slice(0, 3).join(", ")}
                        {student.weak_topics_in_scope.length > 3 ? ` +${student.weak_topics_in_scope.length - 3}` : ""}
                      </p>
                    </div>
                    <Badge tone={student.days_remaining <= 3 ? "red" : "amber"}>{student.days_remaining}d left</Badge>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            icon={<ClipboardCheck className="h-4 w-4" />}
            title="Pending quiz reviews"
            description="AI-generated questions waiting for your approval."
            actions={<Link href="/quiz-review" className="text-sm font-medium text-accent-secondary hover:underline">Review</Link>}
          />
          {!data ? (
            <SkeletonText lines={3} />
          ) : pendingQuizzes.length === 0 ? (
            <EmptyState compact title="You're all caught up" description="Generate a quiz from your uploaded chapters when you're ready." />
          ) : (
            <ul className="flex flex-col divide-y divide-subtle">
              {pendingQuizzes.map(({ quiz, cls }) => {
                const waiting = quiz.questions.filter((q) => q.status === "pending_review").length;
                return (
                  <li key={quiz.id}>
                    <Link href={`/quiz-review?class_id=${cls.id}`} className="group flex items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-primary group-hover:text-accent-secondary">{quiz.title}</p>
                        <p className="truncate text-xs text-tertiary">
                          {cls.name} · {plural(quiz.questions.length, "question")} · {formatRelative(quiz.created_at)}
                        </p>
                      </div>
                      <span className="flex shrink-0 items-center gap-2">
                        <Badge tone={waiting > 0 ? "amber" : "green"}>{waiting > 0 ? `${waiting} to review` : "Ready to publish"}</Badge>
                        <ArrowRight className="h-4 w-4 text-tertiary" aria-hidden />
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader
          icon={<FileText className="h-4 w-4" />}
          title="Recent uploads"
          actions={<Link href="/upload" className="text-sm font-medium text-accent-secondary hover:underline">Manage materials</Link>}
        />
        {!data ? (
          <SkeletonText lines={4} />
        ) : recentDocs.length === 0 ? (
          <EmptyState
            compact
            icon={<FileUp className="h-5 w-5" />}
            title="No documents yet"
            description="Upload your first chapter so the tutor can answer from it."
            action={<ButtonLink href="/upload" variant="primary" size="sm">Upload a chapter</ButtonLink>}
          />
        ) : (
          <ul className="flex flex-col divide-y divide-subtle">
            {recentDocs.map(({ doc, cls }) => (
              <li key={doc.id} className="flex items-center justify-between gap-3 py-3">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-secondary sm:flex" aria-hidden>
                    <FileText className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-primary">{doc.title}</p>
                    <p className="truncate text-xs text-tertiary">
                      {cls.name}
                      {doc.chapter != null ? ` · Ch ${doc.chapter}` : ""} · {formatRelative(doc.created_at)}
                    </p>
                  </div>
                </div>
                <DocumentStatusBadge status={doc.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </PageContainer>
  );
}
