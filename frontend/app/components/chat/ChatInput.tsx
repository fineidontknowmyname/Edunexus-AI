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
                "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
                selected
                  ? "border-accent-secondary bg-accent-secondary/12 text-accent-secondary"
                  : "border-strong bg-surface text-secondary hover:bg-surface-muted hover:text-primary"
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
              <Icon className="h-3.5 w-3.5" aria-hidden />
              {m.label}
            </label>
          );
        })}
        {active && <span className="hidden text-xs text-tertiary sm:inline">{active.description}</span>}
      </fieldset>

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 rounded-2xl border border-strong bg-surface p-2 shadow-sm transition-colors focus-within:border-accent-secondary focus-within:ring-2 focus-within:ring-accent-secondary/25"
      >
        <label htmlFor="chat-message" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-message"
          ref={textareaRef}
          value={value}
          maxLength={CHAT_MESSAGE_MAX_LENGTH}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          rows={1}
          placeholder={placeholder}
          aria-describedby={showCounter ? counterId : undefined}
          className="max-h-[200px] min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-relaxed text-primary placeholder:text-tertiary focus:outline-none focus-visible:outline-none"
        />
        <button
          type="submit"
          disabled={disabled || !trimmed}
          aria-label="Send message"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-primary text-inverse transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <SendHorizontal className="h-4 w-4" aria-hidden />
        </button>
      </form>
      <div className="flex items-center justify-between gap-2 px-1 text-[0.6875rem] text-tertiary">
        <span className="hidden sm:inline">Enter to send · Shift + Enter for a new line</span>
        {showCounter && (
          <span id={counterId} aria-live="polite" className={cn("ml-auto tabular-nums", atLimit ? "font-semibold text-danger" : "text-warning")}>
            {length.toLocaleString()} / {CHAT_MESSAGE_MAX_LENGTH.toLocaleString()}
            {atLimit ? " · limit reached" : ""}
          </span>
        )}
      </div>
    </div>
  );
}
