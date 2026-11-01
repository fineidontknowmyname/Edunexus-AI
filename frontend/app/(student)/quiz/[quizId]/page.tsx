"use client";

import { Suspense, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, ListChecks, Lock, Send } from "lucide-react";
import { apiFetch, ApiError, errorMessage } from "../../../lib/api";
import { useApi } from "../../../lib/hooks/useApi";
import { useClasses } from "../../../lib/hooks/useClasses";
import { useActiveClass } from "../../../lib/hooks/useActiveClass";
import type { QuizAttemptResult, QuizDetail } from "../../../lib/types";
import { Button, ButtonLink } from "../../../components/ui/Button";
import { Alert, EmptyState, ErrorState, PageSkeleton } from "../../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../../components/ui/PageHeader";
import { ProgressBar } from "../../../components/ui/Stat";
import { QuizQuestion } from "../../../components/quiz/QuizQuestion";
import { QuizResults } from "../../../components/quiz/QuizResults";
import { ReflectionPrompt } from "../../../components/reflection/ReflectionPrompt";

export default function QuizTakePage() {
  return (
    <Suspense fallback={<PageContainer width="narrow"><PageSkeleton cards={3} /></PageContainer>}>
      <QuizTakeInner />
    </Suspense>
  );
}

function QuizTakeInner() {
  const router = useRouter();
  const params = useParams<{ quizId: string }>();
  const searchParams = useSearchParams();
  const topicParam = searchParams.get("topic");
  const originParam = searchParams.get("origin");

  const quizQuery = useApi<QuizDetail>(`/quizzes/${params.quizId}`);
  const classes = useClasses();
  const [activeClass] = useActiveClass(classes.data);
  const [answers, setAnswers] = useState<Record<string, string | string[]>>(() => {
    if (typeof window === "undefined") return {};
    try {
      const saved = sessionStorage.getItem(`quiz_in_progress_${params.quizId}`);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // ignore storage errors
    }
    return {};
  });
  const [result, setResult] = useState<QuizAttemptResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<{ message: string; duplicate: boolean } | null>(null);
  const inFlight = useRef(false);

  const quiz = quizQuery.data;

  function handleSelectAnswer(questionId: string, val: string | string[]) {
    setAnswers((prev) => {
      const next = { ...prev, [questionId]: val };
      try {
        sessionStorage.setItem(`quiz_in_progress_${params.quizId}`, JSON.stringify(next));
      } catch {
        // ignore storage errors
      }
      return next;
    });
  }

  const backHref = originParam === "recommendations" ? "/progress" : "/quiz";
  const backLabel = originParam === "recommendations" ? "Back to recommendations" : "All quizzes";

  async function handleSubmit() {
    if (inFlight.current || !quiz) return;
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    setConfirmOpen(false);
    try {
      const res = await apiFetch<QuizAttemptResult>(`/quizzes/${params.quizId}/attempt`, {
        method: "POST",
        body: { answers },
      });
      try {
        sessionStorage.removeItem(`quiz_in_progress_${params.quizId}`);
      } catch {
        // ignore storage errors
      }
      if (res.attempt_id) {
        router.replace(`/quiz/${params.quizId}/attempt/${res.attempt_id}${originParam ? `?origin=${originParam}` : ""}`);
      } else {
        setResult(res);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    } catch (err) {
      const duplicate = err instanceof ApiError && err.status === 409;
      if (duplicate) {
        try {
          sessionStorage.removeItem(`quiz_in_progress_${params.quizId}`);
        } catch {
          // ignore
        }
      }
      setError({
        message: errorMessage(err, duplicate ? "This attempt was already submitted." : "Submission failed. Please try again."),
        duplicate,
      });
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  if (quizQuery.error) {
    return (
      <PageContainer width="narrow">
        <PageHeader title="Quiz" back={{ href: backHref, label: backLabel }} />
        <ErrorState message={quizQuery.error} onRetry={quizQuery.reload} />
      </PageContainer>
    );
  }
  if (!quiz) {
    return (
      <PageContainer width="narrow">
        <PageSkeleton cards={3} />
      </PageContainer>
    );
  }

  if (result) {
    const topicEntries = Object.entries(result.topic_scores);
    const weakestTopic = topicEntries.length === 0 ? null : topicEntries.reduce((a, b) => (b[1] < a[1] ? b : a))[0];

    return (
      <PageContainer width="narrow">
        <PageHeader
          eyebrow={topicParam ? `Topic Assessment Results · ${topicParam}` : "Results"}
          title={quiz.title}
          back={{ href: backHref, label: backLabel }}
          actions={
            <div className="flex items-center gap-2.5">
              <ButtonLink href="/path" variant="secondary">Learning path</ButtonLink>
              <ButtonLink href="/chat" variant="primary">Ask the tutor</ButtonLink>
            </div>
          }
        />
        <QuizResults result={result} quiz={quiz} />
        {activeClass && <ReflectionPrompt classId={activeClass.id} subjectId={activeClass.subject_id} topic={weakestTopic} />}
      </PageContainer>
    );
  }

  const answered = quiz.questions.filter((q) => {
    const a = answers[q.id];
    if (Array.isArray(a)) return a.length > 0;
    return Boolean(a);
  }).length;
  const total = quiz.questions.length;
  const allAnswered = total > 0 && answered === total;

  return (
    <PageContainer width="narrow">
      <PageHeader
        eyebrow={topicParam ? `Topic Assessment Scope: ${topicParam}` : undefined}
        title={quiz.title}
        description={
          topicParam
            ? `Evaluating core concepts and learning objectives for ${topicParam}.`
            : "Carefully answer each question below. You can change answers until you finalize your submission."
        }
        back={{ href: backHref, label: backLabel }}
      />

      {Boolean(quiz.held_question_count && quiz.held_question_count > 0) && (
        <div className="mb-4 rounded-[2px] border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-ink flex items-start gap-3">
          <Lock className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold text-ink">
              {quiz.held_question_count} question{quiz.held_question_count === 1 ? " is" : "s are"} held back:
            </span>{" "}
            Questions on topics you are still working through with the tutor are held back. Review those topics in the tutor chat to unlock them.
            <div className="mt-1.5">
              <Link href="/chat" className="font-mono text-[10px] uppercase tracking-wider text-red hover:underline">
                Review topics in tutor chat ↗
              </Link>
            </div>
          </div>
        </div>
      )}

      {total === 0 ? (
        Boolean(quiz.held_question_count && quiz.held_question_count > 0) ? (
          <EmptyState
            icon={<Lock className="h-6 w-6 text-amber-500" />}
            title="Questions held back by tutor"
            description="Questions on topics you are still working through with the tutor are held back. Review those topics in the tutor chat to unlock them."
            action={
              <Link href="/chat" className="font-mono text-[10px] uppercase tracking-wider text-red hover:underline">
                Open tutor chat ↗
              </Link>
            }
          />
        ) : (
          <EmptyState
            icon={<ListChecks className="h-5 w-5" />}
            title="No questions available right now"
            description="Some questions may be hidden or pending approval. Try another quiz or visit your learning path."
            action={<Link href="/path" className="text-sm font-medium text-accent-red hover:underline">Open learning path</Link>}
          />
        )
      ) : (
        <>
          <div className="flex flex-col gap-4">
            {quiz.questions.map((q, i) => (
              <QuizQuestion
                key={q.id}
                question={q}
                index={i}
                total={total}
                selected={answers[q.id] ?? null}
                onSelect={(val) => handleSelectAnswer(q.id, val)}
                disabled={submitting}
              />
            ))}
          </div>

          <div className="sticky bottom-4 z-10 border border-line bg-surface/95 backdrop-blur-[10px] p-4 rounded-[3px] shadow-[0_18px_48px_rgba(20,18,15,.08)]">
            {error && (
              <Alert
                tone={error.duplicate ? "warning" : "danger"}
                className="mb-3"
                action={error.duplicate ? <Link href={backHref} className="text-sm font-medium underline">{backLabel}</Link> : undefined}
              >
                {error.message}
              </Alert>
            )}

            {confirmOpen && (
              <div className="mb-3 rounded-[2px] border border-line bg-surface2 p-3 text-xs text-ink flex items-center justify-between gap-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.04em]">
                  Ready to submit? Answered <strong className="text-accent-red">{answered}</strong> of <strong>{total}</strong> questions.
                </span>
                <div className="flex gap-2 shrink-0">
                  <Button size="sm" variant="outline" onClick={() => setConfirmOpen(false)}>
                    Review more
                  </Button>
                  <Button size="sm" variant="primary" loading={submitting} onClick={handleSubmit} icon={<CheckCircle2 className="h-3.5 w-3.5" />}>
                    Confirm Submit
                  </Button>
                </div>
              </div>
            )}

            <div className="flex items-center gap-4">
              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-mono uppercase tracking-[0.06em] text-muted" aria-live="polite">
                  {answered} of {total} answered
                </p>
                <ProgressBar value={total ? answered / total : 0} label="Questions answered" className="mt-1.5" />
              </div>
              <Button
                variant="primary"
                onClick={() => setConfirmOpen(true)}
                disabled={answered === 0 || (error?.duplicate ?? false) || confirmOpen}
                loading={submitting}
                icon={<Send className="h-4 w-4" aria-hidden />}
              >
                {submitting ? "Submitting…" : allAnswered ? "Submit quiz" : `Submit (${answered}/${total})`}
              </Button>
            </div>
          </div>
        </>
      )}
    </PageContainer>
  );
}
