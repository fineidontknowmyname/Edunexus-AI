"use client";

import { FormEvent, useState } from "react";
import type { SessionMode } from "../../lib/types";
import { Button } from "../ui/Button";

export function ChatInput({
  mode,
  onModeChange,
  onSend,
  disabled,
}: {
  mode: SessionMode;
  onModeChange: (mode: SessionMode) => void;
  onSend: (message: string) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }

  return (
    <div className="border-t border-subtle bg-surface p-4 flex flex-col gap-2">
      <div className="flex gap-2">
        {(["study", "revision"] as SessionMode[]).map((m) => (
          <button
            key={m}
            onClick={() => onModeChange(m)}
            className={`px-3 py-1 rounded-full text-xs font-medium border ${
              mode === m
                ? "bg-accent-primary text-inverse border-accent-primary"
                : "bg-surface text-secondary border-strong hover:bg-app"
            }`}
          >
            {m === "study" ? "Study (Socratic)" : "Revision (direct)"}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          rows={2}
          placeholder="Ask about your curriculum..."
          className="flex-1 px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary placeholder:text-tertiary resize-none focus:outline-none focus:ring-2 focus:ring-accent-secondary"
        />
        <Button type="submit" disabled={disabled || !text.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
