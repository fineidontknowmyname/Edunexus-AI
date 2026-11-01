"use client";

import { FormEvent, useEffect, useId, useRef } from "react";
import { BookOpen, HelpCircle, SendHorizontal, Zap } from "lucide-react";
import type { SessionMode } from "../../lib/types";
import { CHAT_MESSAGE_MAX_LENGTH } from "../../lib/constants";
import { cn } from "../../lib/cn";

const MODES: { value: SessionMode; label: string; description: string; icon: typeof BookOpen }[] = [
  { value: "study", label: "Study", description: "Step-by-step explanations", icon: BookOpen },
  { value: "revision", label: "Revision", description: "Short, direct answers", icon: Zap },
  { value: "socratic", label: "Socratic", description: "Guided by questions", icon: HelpCircle },
];

const COUNTER_THRESHOLD = CHAT_MESSAGE_MAX_LENGTH - 500;

export function ChatInput({
  mode,
  onModeChange,
  value,
  onChange,
  onSend,
  disabled,
  placeholder = "Ask about your curriculum…",
}: {
  mode: SessionMode;
  onModeChange: (mode: SessionMode) => void;
  value: string;
  onChange: (value: string) => void;
  onSend: (message: string) => void;
  disabled: boolean;
  placeholder?: string;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const counterId = useId();
  const length = value.length;
  const trimmed = value.trim();
  const showCounter = length >= COUNTER_THRESHOLD;
  const atLimit = length >= CHAT_MESSAGE_MAX_LENGTH;

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  function handleSubmit(e?: FormEvent) {
    e?.preventDefault();
    if (!trimmed || disabled || trimmed.length > CHAT_MESSAGE_MAX_LENGTH) return;
    onSend(trimmed);
    onChange("");
  }

  const active = MODES.find((m) => m.value === mode);

  return (
    <div className="flex flex-col gap-2.5">
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">Tutor mode</legend>
        {MODES.map((m) => {
          const selected = mode === m.value;
          const Icon = m.icon;
          return (
            <label
              key={m.value}
              title={m.description}
              className={cn(
                "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 font-mono text-[9px] uppercase tracking-[0.08em] transition-colors select-none",
                selected
                  ? "border-ink bg-ink text-bg font-semibold"
                  : "border-line bg-transparent text-muted hover:text-ink hover:border-ink"
              )}
            >
              <input
                type="radio"
                name="chat-mode"
                value={m.value}
                checked={selected}
                onChange={() => onModeChange(m.value)}
                className="sr-only"
              />
              <Icon className="h-3 w-3" aria-hidden />
              {m.label}
            </label>
          );
        })}
        {active && <span className="hidden font-mono text-[9px] uppercase tracking-wider text-muted sm:inline">[ {active.description} ]</span>}
      </fieldset>

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 rounded-[2px] border border-line bg-surface p-2.5 transition-colors focus-within:border-red"
      >
        <label htmlFor="chat-message" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-message"
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          disabled={disabled}
          placeholder={placeholder}
          rows={1}
          maxLength={CHAT_MESSAGE_MAX_LENGTH}
          className="flex-1 resize-none bg-transparent px-2 py-1 font-sans text-sm text-ink placeholder:text-muted focus:outline-none max-h-48 overflow-y-auto"
        />

        <div className="flex items-center gap-2 shrink-0">
          {showCounter && (
            <span
              id={counterId}
              className={cn("font-mono text-[9px] uppercase", atLimit ? "text-red font-bold" : "text-muted")}
              aria-live="polite"
            >
              {length}/{CHAT_MESSAGE_MAX_LENGTH}
            </span>
          )}
          <button
            type="submit"
            disabled={disabled || !trimmed || atLimit}
            aria-label="Send message"
            className="primary h-9 px-4 text-[9px] cursor-pointer"
          >
            <SendHorizontal className="h-3.5 w-3.5" aria-hidden />
            <span>Send</span>
          </button>
        </div>
      </form>
    </div>
  );
}
