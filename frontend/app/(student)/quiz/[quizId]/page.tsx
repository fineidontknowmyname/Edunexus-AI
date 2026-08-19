"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch, ApiError } from "../../../lib/api";
import type { QuizAttemptResult, QuizDetail } from "../../../lib/types";
import { Card } from "../../../components/ui/Card";
import { Button } from "../../../components/ui/Button";
import { QuizQuestion } from "../../../components/quiz/QuizQuestion";
import { QuizResults } from "../../../components/quiz/QuizResults";

export default function QuizTakePage() {
  const params = useParams<{ quizId: string }>();
  const [quiz, setQuiz] = useState<QuizDetail | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<QuizAttemptResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<QuizDetail>(`/quizzes/${params.quizId}`).then(setQuiz);
  }, [params.quizId]);

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiFetch<QuizAttemptResult>(`/quizzes/${params.quizId}/attempt`, {
        method: "POST",
        body: { answers },
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Submission failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <div className="max-w-2xl mx-auto">
        <QuizResults result={result} />
      </div>
    );
  }

  if (!quiz) return <p className="text-sm text-gray-500">Loading…</p>;

  const allAnswered = quiz.questions.every((q) => answers[q.id]);

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-gray-900">{quiz.title}</h1>
      {quiz.questions.map((q, i) => (
        <QuizQuestion
          key={q.id}
          question={q}
          index={i}
          selected={answers[q.id] ?? null}
          onSelect={(option) => setAnswers((prev) => ({ ...prev, [q.id]: option }))}
          disabled={submitting}
        />
      ))}
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Button onClick={handleSubmit} disabled={!allAnswered} loading={submitting}>
        Submit Quiz
      </Button>
    </div>
  );
}
