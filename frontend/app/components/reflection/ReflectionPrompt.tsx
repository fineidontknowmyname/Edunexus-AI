"use client";

import { useState } from "react";
import { apiFetch } from "../../lib/api";
import type { ReflectionRead } from "../../lib/types";
import { Card } from "../ui/Card";
import { Button } from "../ui/Button";

export function ReflectionPrompt({
  classId,
  subjectId,
  topic,
}: {
  classId: string;
  subjectId?: string | null;
  topic?: string | null;
}) {
  const [dismissed, setDismissed] = useState(false);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (dismissed) return null;

  async function handleShare() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      await apiFetch<ReflectionRead>("/reflections", {
        method: "POST",
        body: { class_id: classId, subject_id: subjectId ?? null, topic: topic ?? null, text: trimmed },
      });
    } catch (err) {
      console.error(err);
    } finally {
      setSubmitting(false);
      setDismissed(true);
    }
  }

  function handleSkip() {
    setDismissed(true);
  }

  return (
    <Card className="mt-4">
      <h3 className="font-semibold text-primary mb-1 text-sm">What's still unclear about this?</h3>
      <p className="text-sm text-tertiary mb-3">A quick note helps us tailor what you see next — totally optional.</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="Share what's still confusing…"
        disabled={submitting}
        className="w-full px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary placeholder:text-tertiary resize-none focus:outline-none focus:ring-2 focus:ring-accent-secondary mb-3"
      />
      <div className="flex gap-2">
        <Button onClick={handleShare} disabled={!text.trim() || submitting} loading={submitting}>
          Share
        </Button>
        <Button variant="secondary" onClick={handleSkip} disabled={submitting}>
          Skip
        </Button>
      </div>
    </Card>
  );
}
