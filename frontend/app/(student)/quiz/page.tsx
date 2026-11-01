"use client";

import Link from "next/link";
import { ListChecks } from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import { formatRelative, percentValue, plural } from "../../lib/format";
import type { AvailableQuiz, ClassRow, QuizAttemptSummary } from "../../lib/types";
import { EmptyState, ErrorState, SkeletonCard } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { StudentClassGate } from "../../components/layout/StudentClassGate";

export default function QuizListPage() {
  return (
    <StudentClassGate>
      {(activeClass, picker) => <QuizList key={activeClass.id} activeClass={activeClass} picker={picker} />}
    </StudentClassGate>
  );
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
        eyebrow="EVALUATION & PRACTICE"
        title="Quizzes & Diagnostic Tests"
        description={`Syllabus-aligned evaluations for ${activeClass.name}. Each submission calibrates your estimated topic mastery.`}
        actions={picker("w-full sm:w-60")}
      />

      {quizzes.error ? (
        <ErrorState message={quizzes.error} onRetry={quizzes.reload} />
      ) : !quizzes.data ? (
        <div className="grid gap-6 sm:grid-cols-2" role="status">
          <span className="sr-only">Loading quizzes…</span>
          {[0, 1, 2, 3].map((i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
      ) : quizzes.data.length === 0 ? (
        <EmptyState
          bracket="QUIZZES"
          icon={<ListChecks className="h-6 w-6 text-red" />}
          title="No quizzes published yet"
          description="Your faculty has not published quizzes for this class yet. In the meantime, you can ask the tutor questions."
          action={
            <Link href="/chat" className="font-mono text-[9px] uppercase tracking-wider text-red hover:underline">
              Open tutor chat ↗
            </Link>
          }
        />
      ) : (
        <div className="course-grid border border-line">
          {quizzes.data.map((q, idx) => {
            const history = byQuiz.get(q.id) ?? [];
            const last = history[0];
            const best = history.reduce((m, a) => Math.max(m, a.score), 0);
            return (
              <article key={q.id} className="course-card">
                <div>
                  <div className="course-meta">
                    <span>QUIZ {String(idx + 1).padStart(2, "0")} / {activeClass.name.toUpperCase()}</span>
                    <span>{plural(q.question_count, "QUESTION")}</span>
                  </div>
                  <div className="book">
                    <div className="mono text-muted">
                      {[
                        q.unit != null && `UNIT ${q.unit}`,
                        q.chapter != null && `CH ${q.chapter}`,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "SYLLABUS"}
                    </div>
                    <h3 className="font-serif text-2xl text-ink leading-tight mt-1">{q.title}</h3>
                    <p className="font-sans text-xs text-muted mt-2 leading-relaxed">
                      {last
                        ? `${plural(history.length, "attempt")} · last completed ${formatRelative(last.completed_at)}`
                        : "Ready for first diagnostic attempt."}
                    </p>
                  </div>
                </div>

                <div>
                  <div className="card-foot">
                    <span>
                      {last ? `BEST: ${percentValue(best)}` : "STATUS: NEW"}
                    </span>
                    <div className="flex items-center gap-3">
                      {last && (
                        <Link
                          href={`/quiz/${q.id}/attempt/${last.id}`}
                          className="text-muted hover:text-ink font-mono uppercase tracking-wider text-[10px]"
                        >
                          VIEW RESULT
                        </Link>
                      )}
                      <Link href={`/quiz/${q.id}`} className="text-red font-mono uppercase tracking-wider">
                        START TEST ↗
                      </Link>
                    </div>
                  </div>
                  <div className="progress-line">
                    <span style={{ width: last ? `${Math.round(best)}%` : "0%" }} />
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </PageContainer>
  );
}
