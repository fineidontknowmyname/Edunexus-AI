"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";
import type { AvailableQuiz, ClassRow } from "../../lib/types";
import { Card } from "../../components/ui/Card";

export default function QuizListPage() {
  const [classes, setClasses] = useState<ClassRow[] | null>(null);
  const [quizzes, setQuizzes] = useState<AvailableQuiz[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<ClassRow[]>("/classes/").then(setClasses);
  }, []);

  useEffect(() => {
    if (!classes || classes.length === 0) {
      setLoading(false);
      return;
    }
    apiFetch<AvailableQuiz[]>(`/quizzes/available?class_id=${classes[0].id}`)
      .then(setQuizzes)
      .finally(() => setLoading(false));
  }, [classes]);

  if (loading) return <p className="text-sm text-gray-500">Loading…</p>;

  if (!classes || classes.length === 0) {
    return <p className="text-sm text-gray-500">Join a class first from the Chat page.</p>;
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-gray-900">Available Quizzes</h1>
      {quizzes.length === 0 ? (
        <p className="text-sm text-gray-500">No quizzes available yet — ask your teacher to generate one.</p>
      ) : (
        quizzes.map((q) => (
          <Link key={q.id} href={`/quiz/${q.id}`}>
            <Card className="hover:border-blue-400 cursor-pointer">
              <h2 className="font-semibold text-gray-900">{q.title}</h2>
              <p className="text-sm text-gray-500">
                Unit {q.unit} · Chapter {q.chapter} · {q.question_count} questions
              </p>
            </Card>
          </Link>
        ))
      )}
    </div>
  );
}
