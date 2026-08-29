"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { apiFetch, ApiError } from "../../../lib/api";
import type { StudentFullContext } from "../../../lib/types";
import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { MasteryBar } from "../../../components/progress/MasteryBar";

export default function StudentDetailPage() {
  const params = useParams<{ studentId: string }>();
  const searchParams = useSearchParams();
  const classId = searchParams.get("class_id") ?? "";

  const [data, setData] = useState<StudentFullContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  useEffect(() => {
    if (!classId) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId]);

  async function load() {
    try {
      const res = await apiFetch<StudentFullContext>(`/progress/student/${params.studentId}?class_id=${classId}`);
      setData(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load student.");
    }
  }

  async function handleAddNote(e: FormEvent) {
    e.preventDefault();
    setSavingNote(true);
    try {
      await apiFetch("/context/notes", {
        method: "POST",
        body: { student_id: params.studentId, class_id: classId, note: noteText },
      });
      setNoteText("");
      await load();
    } finally {
      setSavingNote(false);
    }
  }

  if (!classId) return <p className="text-sm text-danger">Missing class_id in URL.</p>;
  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-tertiary">Loading…</p>;

  const { context, notes, learning_path } = data;
  const masteryEntries = Object.entries(context.mastery);

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-primary">Student Detail</h1>

      <Card>
        <div className="flex items-center gap-4 text-sm">
          <span>Streak: <strong>{context.engagement.current_streak}</strong></span>
          {context.engagement.staleness_flag && <Badge tone="amber">Inactive 5+ days</Badge>}
        </div>
      </Card>

      {context.misconceptions.length > 0 && (
        <Card>
          <h2 className="font-semibold text-primary mb-2">Active misconceptions</h2>
          <div className="flex flex-col gap-1">
            {context.misconceptions.map((m, i) => (
              <p key={i} className="text-sm">
                <span className="font-medium text-primary">{m.topic}</span>
                <span className="text-secondary"> — {m.description}</span>
              </p>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <h2 className="font-semibold text-primary mb-3">Mastery by topic</h2>
        {masteryEntries.length === 0 ? (
          <p className="text-sm text-tertiary">No quiz attempts yet.</p>
        ) : (
          <div className="flex flex-col gap-4">
            {masteryEntries.map(([topic, m]) => (
              <MasteryBar key={topic} topic={topic} score={m.score} trend={m.trend as never} attempts={m.attempts} />
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Learning path</h2>
        <div className="flex flex-col gap-1">
          {learning_path.map((entry) => (
            <div key={entry.topic} className="flex items-center justify-between text-sm">
              <span className="text-primary">{entry.topic}</span>
              <span className="text-tertiary">{Math.round(entry.mastery_score * 100)}%</span>
            </div>
          ))}
        </div>
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Educator notes</h2>
        <form onSubmit={handleAddNote} className="flex gap-2 mb-4">
          <input
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Add a note about this student…"
            className="flex-1 px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary placeholder:text-tertiary"
            required
          />
          <Button type="submit" loading={savingNote}>Add</Button>
        </form>
        <div className="flex flex-col gap-2">
          {notes.length === 0 ? (
            <p className="text-sm text-tertiary">No notes yet.</p>
          ) : (
            notes.map((n) => (
              <div key={n.id} className="text-sm border-t border-subtle pt-2">
                <p className="text-primary">{n.note}</p>
                <p className="text-xs text-tertiary">{new Date(n.created_at).toLocaleString()}</p>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
