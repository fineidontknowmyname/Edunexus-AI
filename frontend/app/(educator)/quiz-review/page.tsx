"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Archive,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  Flag,
  Layers,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { useClassParam, useClasses } from "../../lib/hooks/useClasses";
import { formatRelative, plural } from "../../lib/format";
import type {
  ClassRow,
  CoverageReport,
  Difficulty,
  DocumentRow,
  QuestionReportItem,
  QuestionType,
  QuizQuestionReview,
  QuizSummaryFaculty,
  ReviewStatus,
} from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Modal } from "../../components/ui/Modal";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonCard } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ClassPicker } from "../../components/layout/ClassPicker";
import { ProgressBar } from "../../components/ui/Stat";
import { ReportQuestionDialog } from "../../components/quiz/ReportQuestionDialog";
import { cn } from "../../lib/cn";

const STATUS_BADGE: Record<ReviewStatus, { tone: "gray" | "green" | "red" | "blue"; label: string }> = {
  pending_review: { tone: "gray", label: "Pending Review" },
  draft: { tone: "blue", label: "Draft" },
  approved: { tone: "green", label: "Published" },
  rejected: { tone: "red", label: "Rejected" },
  archived: { tone: "gray", label: "Archived" },
};

export default function QuizReviewPage() {
  return (
    <Suspense fallback={<PageContainer><PageSkeleton /></PageContainer>}>
      <QuizReviewInner />
    </Suspense>
  );
}

function QuizReviewInner() {
  const classes = useClasses();
  const [classId, setClassId] = useClassParam(classes.data);

  if (classes.error) {
    return (
      <PageContainer>
        <PageHeader title="Quiz Management & Review" />
        <ErrorState message={classes.error} onRetry={classes.reload} />
      </PageContainer>
    );
  }
  if (!classes.data) {
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  }

  const activeClass = classes.data.find((c) => c.id === classId);

  return (
    <PageContainer>
      <PageHeader
        eyebrow="[ 03 / EVALUATIONS ]"
        title="Quiz Management & Authoring"
        description="Create, review, inspect curriculum coverage, and publish quizzes aligned to your class syllabus."
        actions={<ClassPicker classes={classes.data} value={classId} onChange={setClassId} />}
      />
      {!activeClass ? (
        <EmptyState
          icon={<ClipboardCheck className="h-5 w-5" />}
          title="Create a class first"
          description="Quizzes are generated from a class's course material."
          action={
            <Link href="/upload" className="font-mono text-xs uppercase tracking-[0.06em] text-accent-red hover:underline">
              Go to Curriculum
            </Link>
          }
        />
      ) : (
        <ClassQuizzes key={activeClass.id} activeClass={activeClass} />
      )}
    </PageContainer>
  );
}

function ClassQuizzes({ activeClass }: { activeClass: ClassRow }) {
  const documents = useApi<DocumentRow[]>(`/documents/?class_id=${activeClass.id}`);
  const quizzesQuery = useApi<QuizSummaryFaculty[]>(`/quizzes?class_id=${activeClass.id}`);
  const [filter, setFilter] = useState<"all" | "draft" | "approved" | "archived">("all");
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [coverageQuizId, setCoverageQuizId] = useState<string | null>(null);

  const readyDocs = (documents.data ?? []).filter((d) => d.status === "ready");
  const allQuizzes = quizzesQuery.data ?? [];
  const filteredQuizzes = allQuizzes.filter((q) => {
    if (filter === "all") return true;
    if (filter === "draft") return q.status === "draft" || q.status === "pending_review";
    if (filter === "approved") return q.status === "approved";
    if (filter === "archived") return q.status === "archived";
    return true;
  });

  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)] lg:items-start">
      <div className="flex flex-col gap-6">
        <GenerateCard
          activeClass={activeClass}
          hasContent={documents.data ? readyDocs.length > 0 : true}
          docs={readyDocs}
          onGenerated={quizzesQuery.reload}
        />
      </div>

      <section aria-labelledby="quizzes-heading" className="flex min-w-0 flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 id="quizzes-heading" className="font-serif text-[18px] text-ink">
              Class Quizzes
            </h2>
            <Badge tone="gray">{plural(filteredQuizzes.length, "quiz", "quizzes")}</Badge>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex gap-1.5 text-xs">
              {(["all", "draft", "approved", "archived"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setFilter(tab)}
                  className={cn(
                    "rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.06em] transition-colors",
                    filter === tab
                      ? "border-ink bg-ink text-bg font-semibold"
                      : "border-line bg-surface text-muted hover:border-ink"
                  )}
                >
                  {tab === "all" ? "All" : tab === "draft" ? "Drafts" : tab}
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setCreateModalOpen(true)}
              icon={<Plus className="h-3.5 w-3.5" />}
            >
              Manual Quiz
            </Button>
          </div>
        </div>

        {quizzesQuery.error && !quizzesQuery.data ? (
          <ErrorState message={quizzesQuery.error} onRetry={quizzesQuery.reload} />
        ) : !quizzesQuery.data ? (
          <SkeletonCard lines={5} />
        ) : filteredQuizzes.length === 0 ? (
          <EmptyState
            icon={<CheckCheck className="h-5 w-5" />}
            title="No quizzes match this filter"
            description="Generate a quiz using AI or create one manually to build assessments for your students."
          />
        ) : (
          filteredQuizzes.map((quiz) => (
            <FacultyQuizCard
              key={quiz.id}
              summary={quiz}
              onUpdated={quizzesQuery.reload}
              onOpenCoverage={() => setCoverageQuizId(quiz.id)}
            />
          ))
        )}

        {createModalOpen && (
          <CreateQuizModal
            activeClass={activeClass}
            open={createModalOpen}
            onClose={() => setCreateModalOpen(false)}
            onCreated={() => {
              setCreateModalOpen(false);
              quizzesQuery.reload();
            }}
          />
        )}

        {coverageQuizId && (
          <CoverageAnalysisModal
            quizId={coverageQuizId}
            open={Boolean(coverageQuizId)}
            onClose={() => setCoverageQuizId(null)}
            onPublished={() => {
              quizzesQuery.reload();
            }}
          />
        )}
      </section>
    </div>
  );
}

function FacultyQuizCard({
  summary,
  onUpdated,
  onOpenCoverage,
}: {
  summary: QuizSummaryFaculty;
  onUpdated: () => void;
  onOpenCoverage: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addQuestionOpen, setAddQuestionOpen] = useState(false);

  // Detailed quiz questions query when expanded
  const detailQuery = useApi<{ id: string; questions: QuizQuestionReview[] }>(
    expanded ? `/quizzes/${summary.id}/faculty` : null
  );

  async function handlePublish() {
    setPublishing(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/${summary.id}/publish`, { method: "POST" });
      onUpdated();
    } catch (err) {
      setError(errorMessage(err, "Publishing failed."));
    } finally {
      setPublishing(false);
    }
  }

  async function handleArchive() {
    setArchiving(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/${summary.id}/archive`, { method: "POST" });
      onUpdated();
    } catch (err) {
      setError(errorMessage(err, "Archiving failed."));
    } finally {
      setArchiving(false);
    }
  }

  async function handleApproveAll() {
    if (!detailQuery.data) return;
    try {
      for (const q of detailQuery.data.questions) {
        if (q.status !== "approved") {
          await apiFetch(`/quizzes/questions/${q.id}`, { method: "PATCH", body: { status: "approved" } });
        }
      }
      detailQuery.reload();
      onUpdated();
    } catch (err) {
      setError(errorMessage(err, "Failed to approve all questions."));
    }
  }

  const badge = STATUS_BADGE[summary.status] || { tone: "gray", label: summary.status };

  return (
    <Card padded={false} as="article">
      <div className="flex flex-col gap-3 border-b border-subtle p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-primary">{summary.title}</h3>
            <Badge tone={badge.tone}>{badge.label}</Badge>
            <span className="rounded bg-surface-muted px-2 py-0.5 text-xs text-muted">
              v{summary.version}
            </span>
          </div>
          <p className="mt-1 text-xs text-tertiary">
            {[
              summary.unit != null && `Unit ${summary.unit}`,
              summary.chapter != null && `Chapter ${summary.chapter}`,
              plural(summary.question_count, "question"),
              summary.passing_percentage ? `Pass: ${summary.passing_percentage}%` : null,
              summary.time_limit_minutes ? `${summary.time_limit_minutes} mins` : null,
              `Created ${formatRelative(summary.created_at)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {summary.description && (
            <p className="mt-1 text-xs text-secondary">{summary.description}</p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={onOpenCoverage}
            icon={<Layers className="h-3.5 w-3.5" />}
          >
            Coverage
          </Button>

          {summary.status !== "approved" && (
            <Button
              size="sm"
              variant="primary"
              loading={publishing}
              disabled={summary.question_count === 0}
              onClick={handlePublish}
              icon={<Send className="h-3.5 w-3.5" />}
            >
              Publish
            </Button>
          )}

          {summary.status !== "archived" && (
            <Button
              size="sm"
              variant="ghost"
              loading={archiving}
              onClick={handleArchive}
              icon={<Archive className="h-3.5 w-3.5" />}
              aria-label="Archive quiz"
            />
          )}

          <Button
            size="sm"
            variant="ghost"
            onClick={() => setExpanded(!expanded)}
            icon={expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          >
            {expanded ? "Hide Questions" : "Questions"}
          </Button>
        </div>
      </div>

      {error && <Alert tone="danger" className="m-4 mb-0">{error}</Alert>}

      {expanded && (
        <div className="p-4 sm:p-6 bg-surface-muted/30 border-t border-subtle">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h4 className="text-sm font-semibold text-primary">
              Question Authoring ({detailQuery.data?.questions.length ?? summary.question_count})
            </h4>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={handleApproveAll}
                icon={<CheckCheck className="h-3.5 w-3.5" />}
              >
                Approve All
              </Button>
              <Button
                size="sm"
                variant="primary"
                onClick={() => setAddQuestionOpen(true)}
                icon={<Plus className="h-3.5 w-3.5" />}
              >
                Add Question
              </Button>
            </div>
          </div>

          {detailQuery.error ? (
            <ErrorState message={detailQuery.error} onRetry={detailQuery.reload} />
          ) : !detailQuery.data ? (
            <SkeletonCard lines={3} />
          ) : detailQuery.data.questions.length === 0 ? (
            <p className="text-xs text-muted">No questions yet. Click Add Question to author one.</p>
          ) : (
            <ol className="divide-y divide-subtle rounded-xl border border-subtle bg-surface">
              {detailQuery.data.questions.map((q, i) => (
                <QuestionItem
                  key={q.id}
                  question={q}
                  index={i}
                  canMoveUp={i > 0}
                  canMoveDown={i < (detailQuery.data?.questions.length ?? 0) - 1}
                  onMoveUp={async () => {
                    if (!detailQuery.data) return;
                    const reordered = [...detailQuery.data.questions];
                    const [moved] = reordered.splice(i, 1);
                    reordered.splice(i - 1, 0, moved);
                    try {
                      await apiFetch(`/quizzes/${summary.id}/reorder`, {
                        method: "POST",
                        body: { question_ids: reordered.map((item) => item.id) },
                      });
                      detailQuery.reload();
                      onUpdated();
                    } catch (err) {
                      console.error("Failed to reorder:", err);
                    }
                  }}
                  onMoveDown={async () => {
                    if (!detailQuery.data) return;
                    const reordered = [...detailQuery.data.questions];
                    const [moved] = reordered.splice(i, 1);
                    reordered.splice(i + 1, 0, moved);
                    try {
                      await apiFetch(`/quizzes/${summary.id}/reorder`, {
                        method: "POST",
                        body: { question_ids: reordered.map((item) => item.id) },
                      });
                      detailQuery.reload();
                      onUpdated();
                    } catch (err) {
                      console.error("Failed to reorder:", err);
                    }
                  }}
                  onChanged={() => {
                    detailQuery.reload();
                    onUpdated();
                  }}
                />
              ))}
            </ol>
          )}

          {addQuestionOpen && (
            <AddQuestionModal
              quizId={summary.id}
              open={addQuestionOpen}
              onClose={() => setAddQuestionOpen(false)}
              onAdded={() => {
                setAddQuestionOpen(false);
                detailQuery.reload();
                onUpdated();
              }}
            />
          )}
        </div>
      )}
    </Card>
  );
}

function QuestionItem({
  question,
  index,
  canMoveUp,
  canMoveDown,
  onMoveUp,
  onMoveDown,
  onChanged,
}: {
  question: QuizQuestionReview;
  index: number;
  canMoveUp?: boolean;
  canMoveDown?: boolean;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [reportsOpen, setReportsOpen] = useState(false);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [reportsList, setReportsList] = useState<QuestionReportItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  async function handleRegenerate() {
    if (!confirm("Replace this question with a newly generated one?")) return;
    setRegenerating(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/questions/${question.id}/regenerate`, { method: "POST" });
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Failed to regenerate question."));
    } finally {
      setRegenerating(false);
    }
  }

  async function handleToggleReports() {
    if (reportsOpen) {
      setReportsOpen(false);
      return;
    }
    setReportsOpen(true);
    if (reportsList === null) {
      setReportsLoading(true);
      setReportsError(null);
      try {
        const res = await apiFetch<QuestionReportItem[]>(`/quizzes/questions/${question.id}/reports`);
        setReportsList(res);
      } catch (err) {
        setReportsError(errorMessage(err, "Failed to load reports."));
      } finally {
        setReportsLoading(false);
      }
    }
  }

  async function setStatus(status: "approved" | "rejected") {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/questions/${question.id}`, { method: "PATCH", body: { status } });
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Failed to update status."));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Are you sure you want to delete this question?")) return;
    setBusy(true);
    try {
      await apiFetch(`/quizzes/questions/${question.id}`, { method: "DELETE" });
      onChanged();
    } catch (err) {
      setError(errorMessage(err, "Cannot delete question."));
    } finally {
      setBusy(false);
    }
  }

  const badge = STATUS_BADGE[question.status];
  const qType = question.question_type || "single_choice";
  const points = question.points ?? 1.0;

  return (
    <li className={cn("p-4 sm:p-5", question.status === "rejected" && "opacity-60")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-tertiary">#{index + 1}</span>
            <span className="rounded bg-surface-muted px-2 py-0.5 text-xs font-medium text-secondary capitalize">
              {qType.replace("_", " ")}
            </span>
            <span className="rounded-[2px] border border-line bg-surface2 px-2 py-0.5 font-mono text-[11px] font-medium text-ink">
              {points} pt{points === 1 ? "" : "s"}
            </span>
            {question.partial_credit_allowed && (
              <span className="rounded bg-success/10 px-2 py-0.5 text-xs text-success">
                Partial Credit
              </span>
            )}
            <Badge tone={badge.tone}>{badge.label}</Badge>
            {Boolean(question.report_count && question.report_count > 0) && (
              <button
                type="button"
                onClick={handleToggleReports}
                className="rounded bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning hover:bg-warning/20 transition-colors"
              >
                {question.report_count} report{question.report_count === 1 ? "" : "s"}
              </button>
            )}
          </div>
          <p className="text-sm font-medium text-primary">{question.question_text}</p>
        </div>
        <div className="flex items-center gap-1">
          {onMoveUp && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy || regenerating || !canMoveUp}
              onClick={onMoveUp}
              icon={<ChevronUp className="h-3.5 w-3.5" />}
              aria-label="Move question up"
            />
          )}
          {onMoveDown && (
            <Button
              size="sm"
              variant="ghost"
              disabled={busy || regenerating || !canMoveDown}
              onClick={onMoveDown}
              icon={<ChevronDown className="h-3.5 w-3.5" />}
              aria-label="Move question down"
            />
          )}
          <Button
            size="sm"
            variant="ghost"
            disabled={busy || regenerating}
            onClick={() => setEditOpen(true)}
            icon={<Pencil className="h-3.5 w-3.5" />}
            aria-label="Edit question"
          />
          <Button
            size="sm"
            variant="ghost"
            disabled={busy || regenerating}
            onClick={handleDelete}
            icon={<Trash2 className="h-3.5 w-3.5 text-danger" />}
            aria-label="Delete question"
          />
        </div>
      </div>

      <ul className="mt-2.5 grid gap-1.5 sm:grid-cols-2">
        {question.options.map((opt) => {
          const isCorrect = Array.isArray(question.correct_answer)
            ? question.correct_answer.includes(opt)
            : opt === question.correct_answer;
          return (
            <li
              key={opt}
              className={cn(
                "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
                isCorrect
                  ? "border-success/40 bg-success/8 font-medium text-success"
                  : "border-subtle text-secondary"
              )}
            >
              {isCorrect ? <Check className="mt-px h-3.5 w-3.5 shrink-0" /> : <span className="h-3.5 w-3.5 shrink-0" />}
              {opt}
            </li>
          );
        })}
      </ul>

      {question.explanation && (
        <p className="mt-2 text-xs italic text-muted">Explanation: {question.explanation}</p>
      )}

      {(question.provenance || question.source_page_number != null) && (
        <details className="mt-2 text-[11px] text-muted font-mono">
          <summary className="cursor-pointer hover:text-ink select-none uppercase tracking-wider">
            [+] Source &amp; Validation
          </summary>
          <div className="mt-1.5 p-2.5 rounded-[2px] border border-line bg-surface2 flex flex-col gap-1">
            {question.source_page_number != null && (
              <div><span className="text-muted">Source:</span> Page {question.source_page_number}</div>
            )}
            {question.topic && (
              <div><span className="text-muted">Topic:</span> {question.topic}</div>
            )}
            {(question.provenance?.bloom_level || question.curriculum_mappings?.[0]?.bloom_level) && (
              <div>
                <span className="text-muted">Bloom Level:</span>{" "}
                {question.provenance?.bloom_level || question.curriculum_mappings?.[0]?.bloom_level}
              </div>
            )}
            {question.provenance?.generator && (
              <div>
                <span className="text-muted">Generator:</span> {question.provenance.generator}
                {question.provenance.prompt_version ? ` (${question.provenance.prompt_version})` : ""}
              </div>
            )}
            <div>
              <span className="text-muted">Validation:</span> validated: schema, duplicate, grounding
            </div>
          </div>
        </details>
      )}

      {reportsOpen && (
        <div className="mt-3 rounded-[2px] border border-line bg-surface2 p-3 text-xs">
          <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-wider text-muted mb-2">
            <span>Question Reports ({reportsList?.length ?? question.report_count ?? 0})</span>
            <button
              type="button"
              onClick={() => setReportsOpen(false)}
              className="text-muted hover:text-ink font-sans"
            >
              ✕
            </button>
          </div>
          {reportsLoading && <p className="text-muted">Loading reports…</p>}
          {reportsError && <p className="text-red">{reportsError}</p>}
          {reportsList && reportsList.length === 0 && (
            <p className="text-muted">No details found for reports.</p>
          )}
          {reportsList && reportsList.length > 0 && (
            <ul className="flex flex-col gap-2 divide-y divide-line/40">
              {reportsList.map((rep) => (
                <li key={rep.id} className="pt-2 first:pt-0">
                  <div className="flex items-center justify-between gap-2 font-mono text-[10px] text-muted">
                    <span className="font-semibold uppercase text-ink">{rep.category.replace(/_/g, " ")}</span>
                    <span>{new Date(rep.created_at).toLocaleDateString()}</span>
                  </div>
                  {rep.comment && (
                    <p className="mt-1 font-sans text-xs text-ink">{rep.comment}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {error && <Alert tone="danger" className="mt-2">{error}</Alert>}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-tertiary">
          {question.topic ? `Topic: ${question.topic}` : "Unmapped topic"} · <span className="capitalize">{question.difficulty}</span>
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          {(question.status === "pending_review" || question.status === "rejected") && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy || regenerating}
              loading={regenerating}
              onClick={handleRegenerate}
              icon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              Regenerate
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            disabled={busy || regenerating}
            onClick={() => setReportOpen(true)}
            icon={<Flag className="h-3.5 w-3.5 text-muted" />}
          >
            Report
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={busy || regenerating}
            onClick={() => setEditOpen(true)}
            icon={<Pencil className="h-3.5 w-3.5" />}
          >
            Edit
          </Button>
          <Button
            variant={question.status === "approved" ? "accent" : "secondary"}
            size="sm"
            disabled={busy || regenerating || question.status === "approved"}
            loading={busy}
            onClick={() => setStatus("approved")}
            icon={<Check className="h-3.5 w-3.5" />}
          >
            Approve
          </Button>
          <Button
            variant={question.status === "rejected" ? "danger" : "ghost"}
            size="sm"
            disabled={busy || regenerating || question.status === "rejected"}
            onClick={() => setStatus("rejected")}
            icon={<X className="h-3.5 w-3.5" />}
          >
            Reject
          </Button>
        </div>
      </div>

      {editOpen && (
        <EditQuestionModal
          question={question}
          open={editOpen}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            setEditOpen(false);
            onChanged();
          }}
        />
      )}
      {reportOpen && (
        <ReportQuestionDialog
          questionId={question.id}
          open={reportOpen}
          onClose={() => setReportOpen(false)}
        />
      )}
    </li>
  );
}

function CreateQuizModal({
  activeClass,
  open,
  onClose,
  onCreated,
}: {
  activeClass: ClassRow;
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState<number | "">("");
  const [chapter, setChapter] = useState<number | "">("");
  const [passingPercentage, setPassingPercentage] = useState(70);
  const [timeLimitMinutes, setTimeLimitMinutes] = useState<number | "">("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await apiFetch("/quizzes", {
        method: "POST",
        body: {
          class_id: activeClass.id,
          title: title.trim(),
          description: description.trim() || null,
          unit: unit === "" ? null : Number(unit),
          chapter: chapter === "" ? null : Number(chapter),
          passing_percentage: Number(passingPercentage),
          time_limit_minutes: timeLimitMinutes === "" ? null : Number(timeLimitMinutes),
        },
      });
      onCreated();
    } catch (err) {
      setError(errorMessage(err, "Failed to create quiz."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create Manual Quiz"
      description="Define the quiz parameters. You can add questions and map them to syllabus topics next."
    >
      <form onSubmit={handleCreate} className="flex flex-col gap-3">
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="e.g. Unit 3 Diagnostic Assessment" />
        <Input label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Overview or instructions for students" />
        <div className="grid grid-cols-2 gap-2">
          <Input label="Unit" type="number" min={1} value={unit} onChange={(e) => setUnit(e.target.value ? Number(e.target.value) : "")} />
          <Input label="Chapter" type="number" min={1} value={chapter} onChange={(e) => setChapter(e.target.value ? Number(e.target.value) : "")} />
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Input label="Passing Score %" type="number" min={1} max={100} value={passingPercentage} onChange={(e) => setPassingPercentage(Number(e.target.value))} />
          <Input label="Time Limit (mins)" type="number" min={1} value={timeLimitMinutes} onChange={(e) => setTimeLimitMinutes(e.target.value ? Number(e.target.value) : "")} />
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" loading={saving} disabled={!title.trim()}>Create Quiz</Button>
        </div>
      </form>
    </Modal>
  );
}

function AddQuestionModal({
  quizId,
  open,
  onClose,
  onAdded,
}: {
  quizId: string;
  open: boolean;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [questionText, setQuestionText] = useState("");
  const [questionType, setQuestionType] = useState<QuestionType>("single_choice");
  const [optionsText, setOptionsText] = useState("Option A\nOption B\nOption C\nOption D");
  const [correctAnswer, setCorrectAnswer] = useState("Option A");
  const [points, setPoints] = useState(1.0);
  const [partialCredit, setPartialCredit] = useState(false);
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [explanation, setExplanation] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    let parsedOptions: string[];
    if (questionType === "true_false") {
      parsedOptions = ["True", "False"];
    } else {
      parsedOptions = optionsText.split("\n").map((o) => o.trim()).filter(Boolean);
      if (parsedOptions.length < 2) {
        setError("Please provide at least 2 options.");
        setSaving(false);
        return;
      }
    }

    let parsedCorrect: string | string[];
    if (questionType === "multiple_choice") {
      parsedCorrect = correctAnswer.split(",").map((c) => c.trim()).filter(Boolean);
      if (parsedCorrect.length === 0) {
        setError("Please specify correct answer(s) separated by commas.");
        setSaving(false);
        return;
      }
    } else {
      parsedCorrect = correctAnswer.trim();
    }

    try {
      await apiFetch(`/quizzes/${quizId}/questions`, {
        method: "POST",
        body: {
          question_text: questionText.trim(),
          question_type: questionType,
          options: parsedOptions,
          correct_answer: parsedCorrect,
          points: Number(points),
          partial_credit_allowed: questionType === "multiple_choice" ? partialCredit : false,
          topic: topic.trim() || null,
          difficulty,
          explanation: explanation.trim() || null,
        },
      });
      onAdded();
    } catch (err) {
      setError(errorMessage(err, "Failed to add question."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Add Question">
      <form onSubmit={handleAdd} className="flex flex-col gap-3">
        <Input label="Question Text" value={questionText} onChange={(e) => setQuestionText(e.target.value)} required placeholder="e.g. Which organelle is responsible for ATP synthesis?" />

        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs font-medium text-secondary">
            Question Type
            <select
              value={questionType}
              onChange={(e) => {
                const val = e.target.value as QuestionType;
                setQuestionType(val);
                if (val === "true_false") {
                  setOptionsText("True\nFalse");
                  setCorrectAnswer("True");
                }
              }}
              className="mt-1 w-full rounded-lg border border-control-line bg-surface px-3 py-2 text-sm text-primary"
            >
              <option value="single_choice">Single Choice</option>
              <option value="multiple_choice">Multiple Choice</option>
              <option value="true_false">True / False</option>
            </select>
          </label>

          <label className="text-xs font-medium text-secondary">
            Difficulty
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as Difficulty)}
              className="mt-1 w-full rounded-lg border border-control-line bg-surface px-3 py-2 text-sm text-primary"
            >
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
        </div>

        {questionType !== "true_false" && (
          <label className="text-xs font-medium text-secondary">
            Options (one per line)
            <textarea
              rows={4}
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              className="mt-1 w-full rounded-lg border border-control-line bg-surface p-2 text-sm text-primary"
              required
            />
          </label>
        )}

        <Input
          label={questionType === "multiple_choice" ? "Correct Answers (comma-separated)" : "Correct Answer"}
          value={correctAnswer}
          onChange={(e) => setCorrectAnswer(e.target.value)}
          required
          placeholder={questionType === "multiple_choice" ? "Option A, Option B" : "Option A"}
        />

        <div className="grid grid-cols-2 gap-2">
          <Input label="Points" type="number" min={0.5} step={0.5} value={points} onChange={(e) => setPoints(Number(e.target.value))} />
          <Input label="Curriculum Topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. Cellular Respiration" />
        </div>

        {questionType === "multiple_choice" && (
          <label className="flex items-center gap-2 text-xs text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={partialCredit}
              onChange={(e) => setPartialCredit(e.target.checked)}
              className="rounded border-subtle"
            />
            Allow partial credit for partially correct choices
          </label>
        )}

        <Input label="Explanation (shown to students upon review)" value={explanation} onChange={(e) => setExplanation(e.target.value)} placeholder="Rationale or textbook reference" />

        {error && <Alert tone="danger">{error}</Alert>}
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" loading={saving} disabled={!questionText.trim()}>Save Question</Button>
        </div>
      </form>
    </Modal>
  );
}

function EditQuestionModal({
  question,
  open,
  onClose,
  onSaved,
}: {
  question: QuizQuestionReview;
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [questionText, setQuestionText] = useState(question.question_text || "");
  const [questionType, setQuestionType] = useState<QuestionType>(question.question_type || "single_choice");
  const [optionsText, setOptionsText] = useState(() => (question.options ? question.options.join("\n") : ""));
  const [correctAnswer, setCorrectAnswer] = useState(() => {
    if (Array.isArray(question.correct_answer)) {
      return question.correct_answer.join(", ");
    }
    if (typeof question.correct_answer === "string" && question.correct_answer.startsWith("[")) {
      try {
        const parsed = JSON.parse(question.correct_answer);
        if (Array.isArray(parsed)) return parsed.join(", ");
      } catch {}
    }
    return String(question.correct_answer || "");
  });
  const [points, setPoints] = useState(question.points ?? 1.0);
  const [partialCredit, setPartialCredit] = useState(Boolean(question.partial_credit_allowed));
  const [topic, setTopic] = useState(question.topic || "");
  const [difficulty, setDifficulty] = useState<Difficulty>(question.difficulty || "medium");
  const [explanation, setExplanation] = useState(question.explanation || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpdate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    let parsedOptions: string[];
    if (questionType === "true_false") {
      parsedOptions = ["True", "False"];
    } else {
      parsedOptions = optionsText.split("\n").map((o) => o.trim()).filter(Boolean);
      if (parsedOptions.length < 2) {
        setError("Please provide at least 2 options.");
        setSaving(false);
        return;
      }
    }

    let parsedCorrect: string | string[];
    if (questionType === "multiple_choice") {
      parsedCorrect = correctAnswer.split(",").map((c) => c.trim()).filter(Boolean);
      if (parsedCorrect.length === 0) {
        setError("Please specify correct answer(s) separated by commas.");
        setSaving(false);
        return;
      }
    } else {
      parsedCorrect = correctAnswer.trim();
    }

    try {
      await apiFetch(`/quizzes/questions/${question.id}`, {
        method: "PUT",
        body: {
          question_text: questionText.trim(),
          question_type: questionType,
          options: parsedOptions,
          correct_answer: parsedCorrect,
          points: Number(points),
          partial_credit_allowed: questionType === "multiple_choice" ? partialCredit : false,
          topic: topic.trim() || null,
          difficulty,
          explanation: explanation.trim() || null,
        },
      });
      onSaved();
    } catch (err) {
      setError(errorMessage(err, "Failed to update question."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Edit Question">
      <form onSubmit={handleUpdate} className="flex flex-col gap-3">
        <Input
          label="Question Text"
          value={questionText}
          onChange={(e) => setQuestionText(e.target.value)}
          required
          placeholder="e.g. Which organelle is responsible for ATP synthesis?"
        />

        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs font-medium text-secondary">
            Question Type
            <select
              value={questionType}
              onChange={(e) => {
                const val = e.target.value as QuestionType;
                setQuestionType(val);
                if (val === "true_false") {
                  setOptionsText("True\nFalse");
                  setCorrectAnswer("True");
                }
              }}
              className="mt-1 w-full rounded-lg border border-control-line bg-surface px-3 py-2 text-sm text-primary"
            >
              <option value="single_choice">Single Choice</option>
              <option value="multiple_choice">Multiple Choice</option>
              <option value="true_false">True / False</option>
            </select>
          </label>

          <label className="text-xs font-medium text-secondary">
            Difficulty
            <select
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value as Difficulty)}
              className="mt-1 w-full rounded-lg border border-control-line bg-surface px-3 py-2 text-sm text-primary"
            >
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
        </div>

        {questionType !== "true_false" && (
          <label className="text-xs font-medium text-secondary">
            Options (one per line)
            <textarea
              rows={4}
              value={optionsText}
              onChange={(e) => setOptionsText(e.target.value)}
              className="mt-1 w-full rounded-lg border border-control-line bg-surface p-2 text-sm text-primary"
              required
            />
          </label>
        )}

        <Input
          label={questionType === "multiple_choice" ? "Correct Answers (comma-separated)" : "Correct Answer"}
          value={correctAnswer}
          onChange={(e) => setCorrectAnswer(e.target.value)}
          required
          placeholder={questionType === "multiple_choice" ? "Option A, Option B" : "Option A"}
        />

        <div className="grid grid-cols-2 gap-2">
          <Input
            label="Points"
            type="number"
            min={0.5}
            step={0.5}
            value={points}
            onChange={(e) => setPoints(Number(e.target.value))}
          />
          <Input
            label="Curriculum Topic"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="e.g. Cellular Respiration"
          />
        </div>

        {questionType === "multiple_choice" && (
          <label className="flex items-center gap-2 text-xs text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={partialCredit}
              onChange={(e) => setPartialCredit(e.target.checked)}
              className="rounded border-subtle"
            />
            Allow partial credit for partially correct choices
          </label>
        )}

        <Input
          label="Explanation (shown to students upon review)"
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
          placeholder="Rationale or textbook reference"
        />

        {error && <Alert tone="danger">{error}</Alert>}
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" loading={saving} disabled={!questionText.trim()}>
            Save Changes
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function CoverageAnalysisModal({
  quizId,
  open,
  onClose,
  onPublished,
}: {
  quizId: string;
  open: boolean;
  onClose: () => void;
  onPublished: () => void;
}) {
  const coverage = useApi<CoverageReport>(`/quizzes/${quizId}/coverage`);
  const [recalculating, setRecalculating] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleRecalculate() {
    setRecalculating(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/${quizId}/coverage/recalculate`, { method: "POST" });
      coverage.reload();
    } catch (err) {
      setError(errorMessage(err, "Recalculation failed."));
    } finally {
      setRecalculating(false);
    }
  }

  async function handleAcknowledgeAndPublish() {
    setPublishing(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/${quizId}/coverage/acknowledge`, {
        method: "POST",
        body: { faculty_notes: notes.trim() || null },
      });
      await apiFetch(`/quizzes/${quizId}/publish`, { method: "POST" });
      onPublished();
      onClose();
    } catch (err) {
      setError(errorMessage(err, "Failed to publish quiz."));
    } finally {
      setPublishing(false);
    }
  }

  const report = coverage.data;
  const score = report?.coverage_score ?? 0;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Curriculum Coverage & Quality Audit"
      description="Inspect how well this quiz aligns to syllabus topics, learning objectives, and detects coverage gaps."
    >
      {coverage.error ? (
        <ErrorState message={coverage.error} onRetry={coverage.reload} />
      ) : !report ? (
        <SkeletonCard lines={4} />
      ) : (
        <div className="flex flex-col gap-4 text-xs">
          <div className="flex items-center justify-between rounded-xl border border-subtle bg-surface-muted/40 p-4">
            <div>
              <p className="text-sm font-semibold text-primary">Coverage Score</p>
              <p className="text-xs text-muted">
                {report.mapped_questions} of {report.total_questions} questions mapped to syllabus
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={cn(
                "rounded-full px-3 py-1 text-sm font-bold",
                score >= 80 ? "bg-success/10 text-success" : score >= 50 ? "bg-warning/10 text-warning" : "bg-danger/10 text-danger"
              )}>
                {score}%
              </span>
            </div>
          </div>

          <ProgressBar value={score / 100} label="Curriculum Alignment" />

          {report.warnings && report.warnings.length > 0 ? (
            <div className="rounded-xl border border-warning/30 bg-warning/10 p-3.5">
              <div className="flex items-center gap-2 font-semibold text-warning">
                <AlertTriangle className="h-4 w-4" />
                <span>Advisory Quality Warnings ({report.warnings.length})</span>
              </div>
              <ul className="mt-2 list-inside list-disc space-y-1 text-secondary">
                {report.warnings.map((w, i) => (
                  <li key={w.code ? `${w.code}-${i}` : i}>
                    <span className="mr-1.5 rounded bg-warning/20 px-1 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wider text-warning">
                      {w.severity || "advisory"}
                    </span>
                    {w.message}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Alert tone="success">
              All questions are mapped to syllabus objectives with balanced coverage.
            </Alert>
          )}

          {report.coverage_matrix && report.coverage_matrix.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="font-semibold text-primary">Topic Matrix Breakdown</p>
              <div className="max-h-48 overflow-y-auto rounded-lg border border-subtle">
                <table className="w-full text-left text-[0.6875rem]">
                  <thead className="border-b border-subtle bg-surface-muted font-semibold text-secondary">
                    <tr>
                      <th className="p-2">Topic</th>
                      <th className="p-2">Questions</th>
                      <th className="p-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-subtle">
                    {report.coverage_matrix.map((t, idx) => (
                      <tr key={t.topic_id || idx}>
                        <td className="p-2 font-medium text-primary">{t.topic_name || "Unknown Topic"}</td>
                        <td className="p-2">{t.question_count ?? 0}</td>
                        <td className="p-2">
                          <span
                            className={cn(
                              "rounded px-1.5 py-0.5 capitalize",
                              t.status === "covered"
                                ? "bg-success/10 text-success"
                                : t.status === "partially_covered"
                                ? "bg-warning/10 text-warning"
                                : "bg-danger/10 text-danger"
                            )}
                          >
                            {t.status ? t.status.replace("_", " ") : "not covered"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {error && <Alert tone="danger">{error}</Alert>}

          <div className="mt-3 flex flex-col gap-2 border-t border-subtle pt-3">
            {report.warnings && report.warnings.length > 0 && !report.acknowledged && !report.faculty_acknowledged && (
              <Input
                label="Faculty Acknowledgment Notes (optional)"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. Unmapped questions are intentional exploratory items"
              />
            )}

            <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
              <Button
                size="sm"
                variant="secondary"
                loading={recalculating}
                onClick={handleRecalculate}
                icon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                Recalculate
              </Button>

              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={onClose}>
                  Close
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  loading={publishing}
                  onClick={handleAcknowledgeAndPublish}
                  icon={<Send className="h-3.5 w-3.5" />}
                >
                  {report.warnings?.length ? "Acknowledge & Publish" : "Publish Quiz"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

function GenerateCard({
  activeClass,
  hasContent,
  docs,
  onGenerated,
}: {
  activeClass: ClassRow;
  hasContent: boolean;
  docs: DocumentRow[];
  onGenerated: () => void;
}) {
  const [title, setTitle] = useState("");
  const [unit, setUnit] = useState(docs[0]?.unit ?? 1);
  const [chapter, setChapter] = useState(docs[0]?.chapter ?? 1);
  const [numQuestions, setNumQuestions] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleGenerate(e: FormEvent) {
    e.preventDefault();
    setGenerating(true);
    setError(null);
    setSuccess(null);
    try {
      await apiFetch("/quizzes/generate", {
        method: "POST",
        body: { class_id: activeClass.id, title: title.trim(), unit, chapter, num_questions: numQuestions },
      });
      setSuccess(`“${title.trim()}” is ready for review.`);
      setTitle("");
      onGenerated();
    } catch (err) {
      setError(errorMessage(err, "Generation failed."));
    } finally {
      setGenerating(false);
    }
  }

  const chapterOptions = Array.from(new Map(docs.filter((d) => d.chapter != null).map((d) => [`${d.unit}-${d.chapter}`, d])).values());

  return (
    <Card className="lg:sticky lg:top-20">
      <CardHeader icon={<Sparkles className="h-4 w-4" />} title="Generate a quiz" description="Questions are drafted from one chapter of your material." />
      {!hasContent && (
        <Alert tone="warning" className="mb-4" action={<Link href={`/upload?class_id=${activeClass.id}`} className="text-sm font-medium underline">Upload a chapter</Link>}>
          This class has no indexed documents yet, so there&apos;s nothing to generate from.
        </Alert>
      )}
      <form onSubmit={handleGenerate} className="flex flex-col gap-3">
        <Input label="Quiz title" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="e.g. Unit 2: Scheduling check-in" />
        <div className="grid grid-cols-3 gap-2">
          <Input label="Unit" type="number" min={1} value={unit} onChange={(e) => setUnit(Number(e.target.value))} />
          <Input label="Chapter" type="number" min={1} value={chapter} onChange={(e) => setChapter(Number(e.target.value))} />
          <Input label="Questions" type="number" min={1} max={20} value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))} />
        </div>
        {chapterOptions.length > 0 && (
          <div className="flex flex-wrap gap-1.5" aria-label="Uploaded chapters">
            {chapterOptions.map((d) => (
              <button
                key={d.id}
                type="button"
                onClick={() => {
                  setUnit(d.unit ?? 1);
                  setChapter(d.chapter ?? 1);
                }}
                className={cn(
                  "rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-[0.04em] transition-colors",
                  d.unit === unit && d.chapter === chapter ? "border-accent-red bg-accent-red text-on-accent" : "border-control-line bg-surface text-ink hover:border-ink"
                )}
              >
                U{d.unit} · Ch {d.chapter}
              </button>
            ))}
          </div>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        {success && <Alert tone="success">{success}</Alert>}
        <Button type="submit" loading={generating} disabled={!hasContent || !title.trim()}>
          {generating ? "Generating…" : "Generate quiz"}
        </Button>
        {generating && <p className="text-xs text-tertiary">This uses the AI model and can take up to a minute.</p>}
      </form>
    </Card>
  );
}
