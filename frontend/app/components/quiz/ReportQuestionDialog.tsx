"use client";

import { FormEvent, useState } from "react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Alert } from "../ui/Feedback";
import { apiFetch, errorMessage } from "../../lib/api";

export const REPORT_CATEGORIES = [
  { value: "incorrect_question", label: "Incorrect Question / Premise" },
  { value: "incorrect_answer", label: "Incorrect Answer Key" },
  { value: "incorrect_explanation", label: "Incorrect Explanation" },
  { value: "unrelated_topic", label: "Unrelated to Stated Topic" },
  { value: "ambiguous_wording", label: "Ambiguous or Confusing Wording" },
  { value: "incorrect_difficulty", label: "Inappropriate Difficulty Level" },
  { value: "missing_source", label: "Missing or Hallucinated Source Citation" },
  { value: "technical_failure", label: "Formatting or Technical Glitch" },
  { value: "other", label: "Other Academic Concern" },
] as const;

export function ReportQuestionDialog({
  questionId,
  open,
  onClose,
}: {
  questionId: string;
  open: boolean;
  onClose: () => void;
}) {
  const [category, setCategory] = useState<string>("incorrect_answer");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const resp = await apiFetch<{ message?: string }>(`/quizzes/questions/${questionId}/report`, {
        method: "POST",
        body: {
          category,
          comment: comment.trim() || null,
        },
      });
      setSuccess(resp.message || "Feedback submitted successfully.");
      setTimeout(() => {
        onClose();
        setSuccess(null);
        setComment("");
      }, 1500);
    } catch (err) {
      setError(errorMessage(err, "Failed to submit report. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Report Question Issue"
      description="Report an accuracy, quality, or formatting defect for academic review."
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="text-xs font-medium text-secondary">
          Issue Category
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="mt-1 w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-primary"
            required
          >
            {REPORT_CATEGORIES.map((cat) => (
              <option key={cat.value} value={cat.value}>
                {cat.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs font-medium text-secondary">
          Details / Explanation (optional, max 1000 chars)
          <textarea
            rows={4}
            maxLength={1000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Explain why the question or answer is problematic..."
            className="mt-1 w-full rounded-lg border border-subtle bg-surface p-2 text-sm text-primary"
          />
          <span className="mt-0.5 block text-right font-mono text-[10px] text-muted">
            {comment.length}/1000
          </span>
        </label>

        {error && <Alert tone="danger">{error}</Alert>}
        {success && <Alert tone="success">{success}</Alert>}

        <div className="mt-3 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" loading={submitting} disabled={Boolean(success)}>
            Submit Report
          </Button>
        </div>
      </form>
    </Modal>
  );
}
