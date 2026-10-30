"use client";

import { useState } from "react";
import { CheckCircle2, Video } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Input } from "../ui/Input";
import { Button } from "../ui/Button";
import { Alert } from "../ui/Feedback";
import { apiFetch, errorMessage } from "../../lib/api";

interface StudentSuggestVideoModalProps {
  open: boolean;
  onClose: () => void;
  classId: string;
  topic: string;
  onSuggested?: () => void;
}

export function StudentSuggestVideoModal({
  open,
  onClose,
  classId,
  topic,
  onSuggested,
}: StudentSuggestVideoModalProps) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function reset() {
    setUrl("");
    setTitle("");
    setError(null);
    setSuccess(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) {
      setError("Please enter a YouTube video URL.");
      return;
    }
    setSubmitting(true);
    setError(null);

    try {
      await apiFetch("/resources", {
        method: "POST",
        body: {
          class_id: classId,
          topic,
          url: url.trim(),
          title: title.trim(),
          resource_type: "youtube",
        },
      });
      setSuccess(true);
      onSuggested?.();
      setTimeout(() => {
        handleClose();
      }, 2000);
    } catch (err) {
      setError(errorMessage(err, "Failed to submit video suggestion."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Suggest a YouTube Video"
      description={`Share an educational video for '${topic}' with your class. Your educator will review it.`}
    >
      {success ? (
        <div className="flex flex-col items-center justify-center py-6 text-center">
          <CheckCircle2 className="h-12 w-12 text-success" />
          <h4 className="mt-3 text-base font-semibold text-primary">Suggestion Submitted</h4>
          <p className="mt-1 text-sm text-secondary">
            Thank you! Your video was submitted for educator review and will appear once approved.
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && <Alert tone="danger">{error}</Alert>}

          <Input
            label="YouTube Video Link"
            type="url"
            placeholder="https://www.youtube.com/watch?v=..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />

          <Input
            label="Title (Optional)"
            placeholder="Leave blank to automatically fetch video title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={handleClose} disabled={submitting}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={submitting || !url.trim()}
              icon={<Video className="h-4 w-4" />}
            >
              {submitting ? "Submitting…" : "Submit for Review"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
