"use client";

import { useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ListChecks, Send } from "lucide-react";
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
  const params = useParams<{ quizId: string }>();
  const quizQuery = useApi<QuizDetail>(`/quizzes/${params.quizId}`);
  const classes = useClasses();
  const [activeClass] = useActiveClass(classes.data);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizAttemptResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; duplicate: boolean } | null>(null);
  const inFlight = useRef(false);

  const quiz = quizQuery.data;

  async function handleSubmit() {
    if (inFlight.current || !quiz) return;
    inFlight.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<QuizAttemptResult>(`/quizzes/${params.quizId}/attempt`, {
        method: "POST",
        body: { answers },
      });
      setResult(res);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      const duplicate = err instanceof ApiError && err.status === 409;
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
        <PageHeader title="Quiz" back={{ href: "/quiz", label: "All quizzes" }} />
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
          eyebrow="Results"
          title={quiz.title}
          back={{ href: "/quiz", label: "All quizzes" }}
          actions={
            <>
              <ButtonLink href="/path" variant="secondary">Learning path</ButtonLink>
              <ButtonLink href="/chat" variant="primary">Ask the tutor</ButtonLink>
            </>
          }
        />
        <QuizResults result={result} quiz={quiz} />
        {activeClass && <ReflectionPrompt classId={activeClass.id} subjectId={activeClass.subject_id} topic={weakestTopic} />}
      </PageContainer>
    );
  }

  const answered = quiz.questions.filter((q) => answers[q.id]).length;
  const total = quiz.questions.length;
  const allAnswered = total > 0 && answered === total;

  return (
    <PageContainer width="narrow">
      <PageHeader
        title={quiz.title}
        description="Choose one answer per question. You can change answers until you submit."
        back={{ href: "/quiz", label: "All quizzes" }}
      />

      {total === 0 ? (
        <EmptyState
          icon={<ListChecks className="h-5 w-5" />}
          title="No questions available right now"
          description="Some questions may be hidden while you work through a misconception. Try a guided session first."
          action={<Link href="/path" className="text-sm font-medium text-accent-secondary hover:underline">Open learning path</Link>}
        />
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
                onSelect={(option) => setAnswers((prev) => ({ ...prev, [q.id]: option }))}
                disabled={submitting}
              />
            ))}
          </div>

          <div className="sticky bottom-0 z-10 -mx-4 border-t border-subtle bg-app/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border sm:bg-surface/95 sm:px-5 sm:shadow-panel">
            {error && (
              <Alert
                tone={error.duplicate ? "warning" : "danger"}
                className="mb-3"
                action={error.duplicate ? <Link href="/quiz" className="text-sm font-medium underline">Back to quizzes</Link> : undefined}
              >
                {error.message}
              </Alert>
            )}
            <div className="flex items-center gap-4">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-tertiary" aria-live="polite">
                  {answered} of {total} answered
                </p>
                <ProgressBar value={total ? answered / total : 0} label="Questions answered" tone="blue" className="mt-1.5" />
              </div>
              <Button
                onClick={handleSubmit}
                disabled={!allAnswered || (error?.duplicate ?? false)}
                loading={submitting}
                icon={<Send className="h-4 w-4" aria-hidden />}
              >
                {submitting ? "Submitting…" : "Submit quiz"}
              </Button>
            </div>
          </div>
        </>
      )}
    </PageContainer>
  );
}
