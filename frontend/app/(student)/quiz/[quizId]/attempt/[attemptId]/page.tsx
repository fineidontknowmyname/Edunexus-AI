"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useApi } from "../../../../../lib/hooks/useApi";
import { useClasses } from "../../../../../lib/hooks/useClasses";
import { useActiveClass } from "../../../../../lib/hooks/useActiveClass";
import type { QuizAttemptDetail } from "../../../../../lib/types";
import { ButtonLink } from "../../../../../components/ui/Button";
import { ErrorState, PageSkeleton } from "../../../../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../../../../components/ui/PageHeader";
import { QuizResults } from "../../../../../components/quiz/QuizResults";
import { ReflectionPrompt } from "../../../../../components/reflection/ReflectionPrompt";

export default function QuizAttemptViewPage() {
  return (
    <Suspense fallback={<PageContainer width="narrow"><PageSkeleton cards={3} /></PageContainer>}>
      <QuizAttemptViewInner />
    </Suspense>
  );
}

function QuizAttemptViewInner() {
  const params = useParams<{ quizId: string; attemptId: string }>();
  const searchParams = useSearchParams();
  const originParam = searchParams.get("origin");

  const attemptQuery = useApi<QuizAttemptDetail>(`/quizzes/attempts/${params.attemptId}`);
  const classes = useClasses();
  const [activeClass] = useActiveClass(classes.data);

  const backHref = originParam === "recommendations" ? "/progress" : "/quiz";
  const backLabel = originParam === "recommendations" ? "Back to recommendations" : "All quizzes";

  if (attemptQuery.error) {
    return (
      <PageContainer width="narrow">
        <PageHeader title="Quiz Result" back={{ href: backHref, label: backLabel }} />
        <ErrorState message={attemptQuery.error} onRetry={attemptQuery.reload} />
      </PageContainer>
    );
  }

  if (!attemptQuery.data) {
    return (
      <PageContainer width="narrow">
        <PageSkeleton cards={3} />
      </PageContainer>
    );
  }

  const attempt = attemptQuery.data;
  const topicEntries = Object.entries(attempt.topic_scores || {});
  const weakestTopic = topicEntries.length === 0 ? null : topicEntries.reduce((a, b) => (b[1] < a[1] ? b : a))[0];

  return (
    <PageContainer width="narrow">
      <PageHeader
        eyebrow="Evaluation Results"
        title={attempt.quiz_title || "Quiz Evaluation"}
        description={attempt.completed_at ? `Completed on ${new Date(attempt.completed_at).toLocaleDateString()}` : undefined}
        back={{ href: backHref, label: backLabel }}
        actions={
          <div className="flex items-center gap-2.5">
            <ButtonLink href="/path" variant="secondary">Learning path</ButtonLink>
            <ButtonLink href="/chat" variant="primary">Ask the tutor</ButtonLink>
          </div>
        }
      />

      <QuizResults
        result={{
          attempt_id: attempt.attempt_id || attempt.id,
          score: attempt.score,
          topic_scores: attempt.topic_scores || {},
          results: attempt.results || [],
          updated_mastery: attempt.updated_mastery || {},
        }}
        quiz={attempt.quiz}
      />

      {activeClass && (
        <ReflectionPrompt
          classId={activeClass.id}
          subjectId={activeClass.subject_id}
          topic={weakestTopic}
        />
      )}
    </PageContainer>
  );
}
