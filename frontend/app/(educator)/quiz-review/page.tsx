"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { Check, CheckCheck, ClipboardCheck, Send, Sparkles, X } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { useClassParam, useClasses } from "../../lib/hooks/useClasses";
import { formatRelative, plural } from "../../lib/format";
import type { ClassRow, DocumentRow, PendingQuiz, QuizQuestionReview, ReviewStatus } from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonCard } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ClassPicker } from "../../components/layout/ClassPicker";
import { cn } from "../../lib/cn";

const STATUS_BADGE: Record<ReviewStatus, { tone: "gray" | "green" | "red"; label: string }> = {
  pending_review: { tone: "gray", label: "Pending" },
  approved: { tone: "green", label: "Approved" },
  rejected: { tone: "red", label: "Rejected" },
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
        <PageHeader title="Quiz review" />
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
        title="Quiz review"
        description="Generate quizzes from your uploaded chapters, then approve the questions students will see."
        actions={<ClassPicker classes={classes.data} value={classId} onChange={setClassId} />}
      />
      {!activeClass ? (
        <EmptyState
          icon={<ClipboardCheck className="h-5 w-5" />}
          title="Create a class first"
          description="Quizzes are generated from a class's course material."
          action={<Link href="/upload" className="text-sm font-medium text-accent-secondary hover:underline">Go to Curriculum</Link>}
        />
      ) : (
        <ClassQuizzes key={activeClass.id} activeClass={activeClass} />
      )}
    </PageContainer>
  );
}

function ClassQuizzes({ activeClass }: { activeClass: ClassRow }) {
  const documents = useApi<DocumentRow[]>(`/documents/?class_id=${activeClass.id}`);
  const pending = useApi<PendingQuiz[]>(`/quizzes/pending?class_id=${activeClass.id}`);
  const readyDocs = (documents.data ?? []).filter((d) => d.status === "ready");

  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)] lg:items-start">
      <GenerateCard activeClass={activeClass} hasContent={documents.data ? readyDocs.length > 0 : true} docs={readyDocs} onGenerated={pending.reload} />

      <section aria-labelledby="pending-heading" className="flex min-w-0 flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 id="pending-heading" className="text-base font-semibold text-primary">Pending review</h2>
          {pending.data && pending.data.length > 0 && <Badge tone="amber">{plural(pending.data.length, "quiz", "quizzes")}</Badge>}
        </div>
        {pending.error && !pending.data ? (
          <ErrorState message={pending.error} onRetry={pending.reload} />
        ) : !pending.data ? (
          <SkeletonCard lines={5} />
        ) : pending.data.length === 0 ? (
          <EmptyState
            icon={<CheckCheck className="h-5 w-5" />}
            title="Nothing waiting for review"
            description="Generate a quiz and its questions will appear here for approval before students see them."
          />
        ) : (
          pending.data.map((quiz) => (
            <PendingQuizCard
              key={quiz.id}
              quiz={quiz}
              onChange={(updated) => pending.mutate((prev) => prev?.map((q) => (q.id === updated.id ? updated : q)) ?? null)}
              onPublished={(id) => pending.mutate((prev) => prev?.filter((q) => q.id !== id) ?? null)}
            />
          ))
        )}
      </section>
    </div>
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
                  "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                  d.unit === unit && d.chapter === chapter ? "border-accent-secondary bg-accent-secondary/10 text-accent-secondary" : "border-strong text-secondary hover:bg-surface-muted"
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

function PendingQuizCard({
  quiz,
  onChange,
  onPublished,
}: {
  quiz: PendingQuiz;
  onChange: (quiz: PendingQuiz) => void;
  onPublished: (id: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [published, setPublished] = useState(false);
  const approved = quiz.questions.filter((q) => q.status === "approved").length;
  const waiting = quiz.questions.filter((q) => q.status === "pending_review");

  async function setStatus(question: QuizQuestionReview, status: "approved" | "rejected") {
    setBusy(question.id);
    setError(null);
    try {
      await apiFetch(`/quizzes/questions/${question.id}`, { method: "PATCH", body: { status } });
      onChange({ ...quiz, questions: quiz.questions.map((q) => (q.id === question.id ? { ...q, status } : q)) });
    } catch (err) {
      setError(errorMessage(err, "Couldn't update that question."));
    } finally {
      setBusy(null);
    }
  }

  async function approveAll() {
    setBusy("all");
    setError(null);
    let next = quiz;
    try {
      for (const q of waiting) {
        await apiFetch(`/quizzes/questions/${q.id}`, { method: "PATCH", body: { status: "approved" } });
        next = { ...next, questions: next.questions.map((x) => (x.id === q.id ? { ...x, status: "approved" as const } : x)) };
      }
    } catch (err) {
      setError(errorMessage(err, "Couldn't approve every question."));
    } finally {
      onChange(next);
      setBusy(null);
    }
  }

  async function publish() {
    setPublishing(true);
    setError(null);
    try {
      await apiFetch(`/quizzes/${quiz.id}/publish`, { method: "POST" });
      setPublished(true);
      setTimeout(() => onPublished(quiz.id), 1200);
    } catch (err) {
      setError(errorMessage(err, "Publishing failed."));
    } finally {
      setPublishing(false);
    }
  }

  return (
    <Card padded={false} as="article">
      <div className="flex flex-col gap-3 border-b border-subtle p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div className="min-w-0">
          <h3 className="font-semibold text-primary">{quiz.title}</h3>
          <p className="text-xs text-tertiary">
            {[quiz.unit != null && `Unit ${quiz.unit}`, quiz.chapter != null && `Chapter ${quiz.chapter}`, `generated ${formatRelative(quiz.created_at)}`].filter(Boolean).join(" · ")}
          </p>
          <p className="mt-1 text-xs text-secondary">
            {approved} approved · {waiting.length} pending · {quiz.questions.length - approved - waiting.length} rejected
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {waiting.length > 0 && (
            <Button variant="secondary" size="sm" loading={busy === "all"} disabled={busy !== null} onClick={approveAll} icon={<CheckCheck className="h-3.5 w-3.5" aria-hidden />}>
              Approve all
            </Button>
          )}
          <Button size="sm" loading={publishing} disabled={approved === 0 || busy !== null || published} onClick={publish} icon={<Send className="h-3.5 w-3.5" aria-hidden />}>
            Publish {approved > 0 ? `(${approved})` : ""}
          </Button>
        </div>
      </div>
      {published && <Alert tone="success" className="m-5 mb-0 sm:m-6 sm:mb-0">Published. Students can take this quiz now.</Alert>}
      {error && <Alert tone="danger" className="m-5 mb-0 sm:m-6 sm:mb-0">{error}</Alert>}
      <ol className="divide-y divide-subtle">
        {quiz.questions.map((q, i) => {
          const badge = STATUS_BADGE[q.status];
          return (
            <li key={q.id} className={cn("p-5 sm:px-6", q.status === "rejected" && "opacity-60")}>
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium text-primary">
                  <span className="text-tertiary">{i + 1}. </span>
                  {q.question_text}
                </p>
                <Badge tone={badge.tone}>{badge.label}</Badge>
              </div>
              <ul className="mt-2.5 grid gap-1.5 sm:grid-cols-2">
                {q.options.map((opt) => {
                  const correct = opt === q.correct_answer;
                  return (
                    <li
                      key={opt}
                      className={cn(
                        "flex items-start gap-2 rounded-md border px-2.5 py-1.5 text-xs",
                        correct ? "border-success/40 bg-success/8 font-medium text-success" : "border-subtle text-secondary"
                      )}
                    >
                      {correct ? <Check className="mt-px h-3.5 w-3.5 shrink-0" aria-label="Correct answer" /> : <span className="h-3.5 w-3.5 shrink-0" aria-hidden />}
                      {opt}
                    </li>
                  );
                })}
              </ul>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs text-tertiary">
                  {q.topic ?? "No topic"} · <span className="capitalize">{q.difficulty}</span>
                </p>
                <div className="flex gap-1.5">
                  <Button
                    variant={q.status === "approved" ? "accent" : "secondary"}
                    size="sm"
                    disabled={busy !== null || q.status === "approved"}
                    loading={busy === q.id}
                    onClick={() => setStatus(q, "approved")}
                    icon={<Check className="h-3.5 w-3.5" aria-hidden />}
                    aria-label={`Approve question ${i + 1}`}
                  >
                    Approve
                  </Button>
                  <Button
                    variant={q.status === "rejected" ? "danger" : "ghost"}
                    size="sm"
                    disabled={busy !== null || q.status === "rejected"}
                    onClick={() => setStatus(q, "rejected")}
                    icon={<X className="h-3.5 w-3.5" aria-hidden />}
                    aria-label={`Reject question ${i + 1}`}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
