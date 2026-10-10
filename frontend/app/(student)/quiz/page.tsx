"use client";

import Link from "next/link";
import { ArrowRight, ListChecks } from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import { formatRelative, plural } from "../../lib/format";
import type { AvailableQuiz, ClassRow, QuizAttemptSummary } from "../../lib/types";
import { Badge } from "../../components/ui/Badge";
import { EmptyState, ErrorState, SkeletonCard } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { StudentClassGate } from "../../components/layout/StudentClassGate";

export default function QuizListPage() {
  return <StudentClassGate>{(activeClass, picker) => <QuizList key={activeClass.id} activeClass={activeClass} picker={picker} />}</StudentClassGate>;
}

function QuizList({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const quizzes = useApi<AvailableQuiz[]>(`/quizzes/available?class_id=${activeClass.id}`);
  const attempts = useApi<QuizAttemptSummary[]>("/quizzes/attempts/mine");

  const byQuiz = new Map<string, QuizAttemptSummary[]>();
  for (const a of attempts.data ?? []) {
    byQuiz.set(a.quiz_id, [...(byQuiz.get(a.quiz_id) ?? []), a]);
  }

  return (
    <PageContainer>
      <PageHeader
        title="Quizzes"
        description={`Short quizzes from ${activeClass.name}. Each attempt updates your mastery and learning path.`}
        actions={picker()}
      />

      {quizzes.error ? (
        <ErrorState message={quizzes.error} onRetry={quizzes.reload} />
      ) : !quizzes.data ? (
        <div className="grid gap-4 sm:grid-cols-2" role="status">
          <span className="sr-only">Loading quizzes…</span>
          {[0, 1, 2, 3].map((i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
      ) : quizzes.data.length === 0 ? (
        <EmptyState
          icon={<ListChecks className="h-5 w-5" />}
          title="No quizzes available yet"
          description="Your teacher hasn't published a quiz for this class. In the meantime, the tutor can quiz you informally."
          action={
            <Link href="/chat" className="text-sm font-medium text-accent-secondary hover:underline">
              Open tutor chat
            </Link>
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2">
          {quizzes.data.map((q) => {
            const history = byQuiz.get(q.id) ?? [];
            const last = history[0];
            const best = history.reduce((m, a) => Math.max(m, a.score), 0);
            return (
              <li key={q.id}>
                <Link
                  href={`/quiz/${q.id}`}
                  className="group flex h-full flex-col rounded-xl border border-subtle bg-surface p-5 shadow-card transition-colors hover:border-accent-secondary/50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-[0.9375rem] font-semibold text-primary group-hover:text-accent-secondary">{q.title}</h2>
                    {last ? (
                      <Badge tone={best >= 70 ? "green" : best >= 40 ? "amber" : "red"}>Best {Math.round(best)}%</Badge>
                    ) : (
                      <Badge tone="blue">New</Badge>
                    )}
                  </div>
                  <p className="mt-1 text-sm text-tertiary">
                    {[q.unit != null && `Unit ${q.unit}`, q.chapter != null && `Chapter ${q.chapter}`, plural(q.question_count, "question")]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <div className="mt-auto flex items-center justify-between pt-4 text-sm">
                    <span className="text-xs text-tertiary">
                      {last ? `${plural(history.length, "attempt")} · last ${formatRelative(last.completed_at)}` : "Not attempted yet"}
                    </span>
                    <span className="inline-flex items-center gap-1 font-medium text-accent-secondary">
                      {last ? "Retake" : "Start"}
                      <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </PageContainer>
  );
}
