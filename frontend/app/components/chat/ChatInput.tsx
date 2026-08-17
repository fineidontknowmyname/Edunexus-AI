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
    <div className="border-t border-gray-200 bg-white p-4 flex flex-col gap-2">
      <div className="flex gap-2">
        {(["study", "revision"] as SessionMode[]).map((m) => (
          <button
            key={m}
            onClick={() => onModeChange(m)}
            className={`px-3 py-1 rounded-full text-xs font-medium border ${
              mode === m
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
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
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <Button type="submit" disabled={disabled || !text.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
