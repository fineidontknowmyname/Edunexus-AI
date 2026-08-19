"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../lib/api";
import type { ClassRow, DocumentRow, PendingQuiz } from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";

export default function QuizReviewPage() {
  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [classId, setClassId] = useState("");
  const [documents, setDocuments] = useState<DocumentRow[]>([]);

  const [title, setTitle] = useState("");
  const [unit, setUnit] = useState(1);
  const [chapter, setChapter] = useState(1);
  const [numQuestions, setNumQuestions] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  const [pending, setPending] = useState<PendingQuiz[]>([]);
  const [loadingPending, setLoadingPending] = useState(false);
  const [publishing, setPublishing] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<ClassRow[]>("/classes/").then((rows) => {
      setClasses(rows);
      if (rows.length > 0) setClassId(rows[0].id);
    });
  }, []);

  useEffect(() => {
    if (!classId) return;
    apiFetch<DocumentRow[]>(`/documents/?class_id=${classId}`).then(setDocuments);
    loadPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId]);

  async function loadPending() {
    if (!classId) return;
    setLoadingPending(true);
    try {
      const rows = await apiFetch<PendingQuiz[]>(`/quizzes/pending?class_id=${classId}`);
      setPending(rows);
    } finally {
      setLoadingPending(false);
    }
  }

  async function handleGenerate(e: FormEvent) {
    e.preventDefault();
    setGenerating(true);
    setGenError(null);
    try {
      await apiFetch("/quizzes/generate", {
        method: "POST",
        body: {
          class_id: classId,
          title,
          unit,
          chapter,
          num_questions: numQuestions,
        },
      });
      setTitle("");
      await loadPending();
    } catch (err) {
      setGenError(err instanceof ApiError ? err.message : "Generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleQuestionStatus(questionId: string, status: "approved" | "rejected") {
    await apiFetch(`/quizzes/questions/${questionId}`, { method: "PATCH", body: { status } });
    await loadPending();
  }

  async function handlePublish(quizId: string) {
    setPublishing(quizId);
    try {
      await apiFetch(`/quizzes/${quizId}/publish`, { method: "POST" });
      await loadPending();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Publish failed.");
    } finally {
      setPublishing(null);
    }
  }

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-gray-900">Quiz Generation & Review</h1>

      <Card>
        <h2 className="font-semibold text-gray-900 mb-3">Generate a quiz</h2>
        {classes.length > 1 && (
          <select
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm mb-3"
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
          >
            {classes.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        )}
        {documents.length === 0 && classId && (
          <p className="text-xs text-amber-600 mb-3">No documents uploaded to this class yet — generation needs curriculum content.</p>
        )}
        <form onSubmit={handleGenerate} className="flex flex-col gap-3">
          <Input label="Quiz title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <div className="grid grid-cols-3 gap-3">
            <Input label="Unit" type="number" min={1} value={unit} onChange={(e) => setUnit(Number(e.target.value))} />
            <Input label="Chapter" type="number" min={1} value={chapter} onChange={(e) => setChapter(Number(e.target.value))} />
            <Input label="# Questions" type="number" min={1} max={20} value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))} />
          </div>
          {genError && <p className="text-sm text-red-600">{genError}</p>}
          <Button type="submit" loading={generating} disabled={!classId}>
            Generate Quiz
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold text-gray-900 mb-3">Pending review</h2>
        {loadingPending ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : pending.length === 0 ? (
          <p className="text-sm text-gray-500">No quizzes pending review.</p>
        ) : (
          <div className="flex flex-col gap-6">
            {pending.map((quiz) => {
              const approvedCount = quiz.questions.filter((q) => q.status === "approved").length;
              return (
                <div key={quiz.id} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-semibold text-gray-900">{quiz.title}</h3>
                    <Button
                      variant="secondary"
                      loading={publishing === quiz.id}
                      disabled={approvedCount === 0}
                      onClick={() => handlePublish(quiz.id)}
                    >
                      Publish ({approvedCount} approved)
                    </Button>
                  </div>
                  <div className="flex flex-col gap-3">
                    {quiz.questions.map((q) => (
                      <div key={q.id} className="border-t border-gray-100 pt-3">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm text-gray-900 flex-1">{q.question_text}</p>
                          <Badge tone={q.status === "approved" ? "green" : q.status === "rejected" ? "red" : "gray"}>
                            {q.status}
                          </Badge>
                        </div>
                        <ul className="text-xs text-gray-500 mt-1 ml-4 list-disc">
                          {q.options.map((opt) => (
                            <li key={opt} className={opt === q.correct_answer ? "text-green-700 font-medium" : ""}>
                              {opt}
                            </li>
                          ))}
                        </ul>
                        <p className="text-xs text-gray-400 mt-1">Topic: {q.topic ?? "—"} · {q.difficulty}</p>
                        <div className="flex gap-2 mt-2">
                          <button
                            onClick={() => handleQuestionStatus(q.id, "approved")}
                            className="text-xs text-green-700 hover:underline"
                          >
                            Approve
                          </button>
                          <button
                            onClick={() => handleQuestionStatus(q.id, "rejected")}
                            className="text-xs text-red-600 hover:underline"
                          >
                            Reject
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
