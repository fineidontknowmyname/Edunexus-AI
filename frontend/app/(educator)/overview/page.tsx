"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BookOpen,
  ClipboardCheck,
  FileUp,
  School,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { useAsync } from "../../lib/hooks/useApi";
import { useAuth } from "../../lib/hooks/useAuth";
import { useClasses } from "../../lib/hooks/useClasses";
import { firstName, formatRelative, percent, plural } from "../../lib/format";
import type { AtRiskStudent, ClassInsightsResponse, ClassRow, DocumentRow, PendingQuiz } from "../../lib/types";
import { Select } from "../../components/ui/Input";
import { ButtonLink } from "../../components/ui/Button";
import { EmptyState, ErrorState, PageSkeleton, Skeleton } from "../../components/ui/Feedback";
import { PageContainer } from "../../components/ui/PageHeader";
import { KpiStrip, KpiCell, FocusRow } from "../../components/ui/Stat";
import { Avatar } from "../../components/layout/UserMenu";
import { DocumentStatusBadge } from "../../components/educator/DocumentStatusBadge";
import { EducatorResourceCurationCard } from "../../components/resources/EducatorResourceCurationCard";
import { EducatorModerationQueue } from "../../components/resources/EducatorModerationQueue";

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
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const classKey = classes.data ? classes.data.map((c) => c.id).join(",") : null;
  const summaries = useAsync<ClassSummary[]>(classKey === null ? null : `overview:${classKey}`, () =>
    loadSummaries(classes.data ?? [])
  );

  if (classes.error) {
    return (
      <PageContainer width="wide">
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
        <div className="flex flex-col sm:flex-row sm:items-end justify-between pb-7 mb-7 border-b border-line gap-4">
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ EDUCATOR / OVERVIEW ]
            </div>
            <h1 className="font-serif text-4xl sm:text-5xl text-ink leading-[0.95] tracking-tight">
              Welcome, <em className="text-red font-normal">{givenName || "Faculty"}.</em>
            </h1>
            <p className="font-sans text-xs sm:text-sm text-muted mt-2">
              Let&apos;s set up your first class curriculum.
            </p>
          </div>
        </div>
        <EmptyState
          bracket="CLASSES"
          icon={<School className="h-5 w-5" />}
          title="You don't have any classes yet"
          description="Create a class and upload your first syllabus chapter. Students can then enroll and learn with the grounded AI tutor."
          action={<ButtonLink href="/upload" variant="primary">Create a class →</ButtonLink>}
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
      {/* Reference Welcome Hero Area */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between pb-7 mb-7 border-b border-line gap-4">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
            [ EDUCATOR / OVERVIEW ]
          </div>
          <h1 className="font-serif text-4xl sm:text-5xl lg:text-[64px] text-ink leading-[0.95] tracking-tight">
            Teaching, with<br />
            <em className="text-red font-normal">better signals.</em>
          </h1>
          <p className="font-sans text-xs sm:text-sm text-muted mt-3 max-w-xl">
            A concise view of class progress, assessment quality and learner support.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <ButtonLink href="/upload" variant="outline" icon={<FileUp className="h-3.5 w-3.5" aria-hidden />}>
            Upload material ↗
          </ButtonLink>
          <ButtonLink href="/quiz-review" variant="primary" icon={<ClipboardCheck className="h-3.5 w-3.5" aria-hidden />}>
            Generate quiz ↗
          </ButtonLink>
        </div>
      </div>

      {summaries.error && <ErrorState message={summaries.error} onRetry={summaries.reload} />}

      {!data ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 border-b border-line pb-6 gap-4" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 rounded-[2px]" />
          ))}
        </div>
      ) : (
        /* Reference 4-Column KPI Strip */
        <KpiStrip className="mb-8">
          <KpiCell
            label="Active Classes"
            value={String(classes.data.length).padStart(2, "0")}
            caption={`${plural(totalDocs, "document")} indexed`}
          />
          <KpiCell
            label="Awaiting Review"
            value={String(pendingQuestions).padStart(2, "0")}
            caption={`${plural(pendingQuizzes.length, "quiz", "quizzes")} pending`}
            tone={pendingQuestions > 0 ? "red" : undefined}
          />
          <KpiCell
            label="Need Attention"
            value={String(uniqueAtRisk).padStart(2, "0")}
            caption="At-risk learners"
            tone={uniqueAtRisk > 0 ? "red" : undefined}
          />
          <KpiCell
            label="Processing Queue"
            value={String(processing).padStart(2, "0")}
            caption={processing > 0 ? "Indexing chapters" : "All materials ready"}
          />
        </KpiStrip>
      )}

      {/* Reference Two-Column Dashboard Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.35fr_0.8fr] gap-8">
        {/* Left Column: Class Performance */}
        <div className="flex flex-col gap-8">
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ CLASS PERFORMANCE ]
            </div>
            <h3 className="font-serif text-2xl sm:text-[29px] text-ink leading-tight mb-2">
              Subject overview
            </h3>

            <div className="divide-y divide-line mt-4">
              {classes.data.map((cls) => {
                const s = data?.find((x) => x.cls.id === cls.id);
                const avg = s ? classAverage(s.insights) : null;
                const initials = cls.name.slice(0, 2).toUpperCase();

                return (
                  <FocusRow
                    key={cls.id}
                    icon={initials}
                    title={cls.name}
                    description={[
                      cls.subject,
                      cls.semester ? `Semester ${cls.semester}` : null,
                      s ? `${plural(s.documents.length, "doc")}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                    actions={
                      <div className="flex items-center gap-4">
                        <div className="hidden sm:block text-right">
                          <span className="font-mono text-[9px] uppercase tracking-wider text-muted block">
                            Average
                          </span>
                          <span className="font-serif text-xl text-ink">
                            {avg === null ? "—" : percent(avg)}
                          </span>
                        </div>
                        <ButtonLink href={`/insights?class_id=${cls.id}`} variant="outline" size="sm">
                          Insights →
                        </ButtonLink>
                      </div>
                    }
                  />
                );
              })}
            </div>
          </div>

          {/* Pending Quiz Reviews */}
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ QUIZ REVIEW QUEUE ]
            </div>
            <h3 className="font-serif text-2xl sm:text-[29px] text-ink leading-tight mb-2">
              AI-generated assessments
            </h3>

            {!data ? (
              <div className="space-y-3 mt-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : pendingQuizzes.length === 0 ? (
              <EmptyState compact bracket="REVIEWS" title="You're all caught up" description="Generate a quiz from your uploaded curriculum chapters when ready." />
            ) : (
              <div className="divide-y divide-line mt-4">
                {pendingQuizzes.map(({ quiz, cls }) => {
                  const waiting = quiz.questions.filter((q) => q.status === "pending_review").length;
                  return (
                    <div key={quiz.id} className="py-3 flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <h4 className="font-serif text-xl text-ink truncate">{quiz.title}</h4>
                        <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
                          {cls.name} · {plural(quiz.questions.length, "question")} · {formatRelative(quiz.created_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-[9px] uppercase tracking-wider text-red">
                          [ {waiting > 0 ? `${waiting} to review` : "Ready"} ]
                        </span>
                        <ButtonLink href={`/quiz-review?class_id=${cls.id}`} variant="outline" size="sm">
                          Review →
                        </ButtonLink>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Intervention Queue */}
        <div className="flex flex-col gap-8">
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ INTERVENTION QUEUE ]
            </div>
            <h3 className="font-serif text-2xl text-ink leading-tight mb-4">
              Students to review
            </h3>

            {!data ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : atRisk.length === 0 ? (
              <EmptyState compact bracket="INTERVENTIONS" title="No students flagged" description="All learners are currently tracking above readiness thresholds." />
            ) : (
              <div className="divide-y divide-line">
                {atRisk.slice(0, 6).map(({ student, cls }) => (
                  <div key={`${cls.id}-${student.student_id}`} className="py-3 flex items-center gap-3 justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <Avatar name={student.full_name} />
                      <div className="min-w-0">
                        <h4 className="font-serif text-lg text-ink truncate leading-tight">{student.full_name}</h4>
                        <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted truncate">
                          {cls.name} · {student.weak_topics_in_scope.slice(0, 2).join(", ")}
                        </p>
                      </div>
                    </div>
                    <Link
                      href={`/students/${student.student_id}?class_id=${cls.id}&name=${encodeURIComponent(student.full_name)}`}
                      className="font-mono text-[9px] uppercase tracking-[0.1em] text-red hover:underline shrink-0"
                    >
                      REVIEW ↗
                    </Link>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-5 pt-3 border-t border-line">
              <ButtonLink href="/insights" variant="outline" size="sm" className="w-full">
                View all class insights →
              </ButtonLink>
            </div>
          </div>

          {/* Recent Uploads Rail */}
          <div className="bg-surface border border-line p-6 rounded-[2px]">
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
              [ RECENT CURRICULUM UPLOADS ]
            </div>
            <h3 className="font-serif text-2xl text-ink leading-tight mb-4">
              Materials indexed
            </h3>

            {!data ? (
              <div className="space-y-3">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : recentDocs.length === 0 ? (
              <EmptyState
                compact
                bracket="MATERIALS"
                icon={<FileUp className="h-5 w-5" />}
                title="No documents yet"
                description="Upload chapters so the tutor can ground its explanations."
                action={<ButtonLink href="/upload" variant="primary" size="sm">Upload a chapter →</ButtonLink>}
              />
            ) : (
              <div className="divide-y divide-line">
                {recentDocs.map(({ doc, cls }) => (
                  <div key={doc.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-serif text-base text-ink truncate leading-tight">{doc.title}</p>
                      <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
                        {cls.name} · {formatRelative(doc.created_at)}
                      </p>
                    </div>
                    <DocumentStatusBadge status={doc.status} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Resource Curation & Moderation Section */}
      {(() => {
        const activeClass = classes.data.find((c) => c.id === selectedClassId) || classes.data[0] || null;
        if (!activeClass) return null;
        return (
          <section className="mt-10 pt-8 border-t border-line">
            <div className="flex flex-col sm:flex-row sm:items-end justify-between pb-5 mb-5 border-b border-line gap-3">
              <div>
                <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-1">
                  [ MULTIMEDIA & CURATION ]
                </div>
                <h3 className="font-serif text-3xl text-ink leading-tight">
                  Resource curation &amp; moderation
                </h3>
                <p className="font-sans text-xs text-muted mt-1">
                  Curate videos and review student submissions for {activeClass.name}.
                </p>
              </div>
              <div className="flex items-center gap-3">
                {classes.data.length > 1 && (
                  <div className="w-full sm:w-56">
                    <Select
                      label="Select Class"
                      srOnlyLabel
                      value={activeClass.id}
                      onChange={(e) => setSelectedClassId(e.target.value)}
                    >
                      {classes.data.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name} {c.subject ? `(${c.subject})` : ""}
                        </option>
                      ))}
                    </Select>
                  </div>
                )}
                <ButtonLink href="/subjects" variant="outline" size="sm" icon={<BookOpen className="h-3.5 w-3.5" />}>
                  Syllabus &amp; Topics ↗
                </ButtonLink>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <EducatorModerationQueue classId={activeClass.id} />
              <EducatorResourceCurationCard classId={activeClass.id} />
            </div>
          </section>
        );
      })()}
    </PageContainer>
  );
}
