"use client";

import { useState } from "react";
import { MessageCircleQuestion } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import type { ReflectionRead } from "../../lib/types";
import { Card, CardHeader } from "../ui/Card";
import { Button } from "../ui/Button";
import { Textarea } from "../ui/Input";
import { Alert } from "../ui/Feedback";

export function ReflectionPrompt({
  classId,
  subjectId,
  topic,
}: {
  classId: string;
  subjectId?: string | null;
  topic?: string | null;
}) {
  const [state, setState] = useState<"open" | "sent" | "skipped">("open");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state === "skipped") return null;
  if (state === "sent") {
    return <Alert tone="success" title="Thanks for sharing">Your teacher sees anonymised themes from reflections like yours.</Alert>;
  }

  async function handleShare() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiFetch<ReflectionRead>("/reflections", {
        method: "POST",
        body: { class_id: classId, subject_id: subjectId ?? null, topic: topic ?? null, text: trimmed },
      });
      setState("sent");
    } catch (err) {
      setError(errorMessage(err, "Couldn't share your reflection."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<MessageCircleQuestion className="h-4 w-4" />}
        title={topic ? `What's still unclear about ${topic}?` : "What's still unclear?"}
        description="Optional. A quick note helps tailor what you see next."
      />
      <Textarea
        label="Your reflection"
        srOnlyLabel
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        maxLength={2000}
        placeholder="Share what's still confusing…"
        disabled={submitting}
      />
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
      <div className="mt-3 flex gap-2">
        <Button onClick={handleShare} disabled={!text.trim()} loading={submitting}>
          Share
        </Button>
        <Button variant="ghost" onClick={() => setState("skipped")} disabled={submitting}>
          Skip
        </Button>
      </div>
    </Card>
  );
}
