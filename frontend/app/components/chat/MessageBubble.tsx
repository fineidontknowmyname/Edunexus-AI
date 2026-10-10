import { AlertTriangle, Flag, PartyPopper, RotateCw, Sparkles } from "lucide-react";
import type { ChatMessageUI } from "../../lib/types";
import { cn } from "../../lib/cn";
import { EvidenceCard } from "./EvidenceCard";
import { MarkdownMessage } from "./MarkdownMessage";

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1.5" role="status">
      <span className="sr-only">Tutor is thinking</span>
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary [animation-delay:-0.3s]" aria-hidden />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary [animation-delay:-0.15s]" aria-hidden />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tertiary" aria-hidden />
    </span>
  );
}

export function MessageBubble({
  message,
  onFlag,
  onRetry,
  retryDisabled,
}: {
  message: ChatMessageUI;
  onFlag: (messageId: string) => void;
  onRetry: (messageKey: string) => void;
  retryDisabled: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-accent-primary px-4 py-2.5 text-sm leading-relaxed text-inverse shadow-sm sm:max-w-[75%]">
          {message.content}
        </div>
      </div>
    );
  }

  const done = !message.streaming && !message.failed;

  return (
    <div className="flex gap-3">
      <span
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-secondary/12 text-accent-secondary"
        aria-hidden
      >
        <Sparkles className="h-3.5 w-3.5" />
      </span>
      <div className="flex min-w-0 max-w-full flex-1 flex-col gap-2 sm:max-w-[85%]">
        <div
          className={cn(
            "rounded-2xl rounded-tl-md border bg-surface px-4 py-3 shadow-card",
            message.failed ? "border-danger/40" : "border-subtle"
          )}
          aria-busy={message.streaming || undefined}
        >
          {message.content ? (
            <>
              <MarkdownMessage content={message.content} />
              {message.streaming && (
                <span className="mt-2 inline-flex items-center gap-1.5 text-xs text-tertiary" role="status">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-secondary" aria-hidden />
                  Writing…
                </span>
              )}
            </>
          ) : message.streaming ? (
            <TypingDots />
          ) : null}

          {message.failed && (
            <div
              role="alert"
              className={cn("flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:justify-between", message.content && "mt-3 border-t border-subtle pt-3")}
            >
              <span className="flex items-start gap-2 text-danger">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <span>{message.errorDetail ?? "Something went wrong."}</span>
              </span>
              {message.retryMessage && (
                <button
                  type="button"
                  onClick={() => onRetry(message.key)}
                  disabled={retryDisabled}
                  className="inline-flex h-8 shrink-0 items-center gap-1.5 self-start rounded-lg border border-strong bg-surface px-3 text-xs font-medium text-primary hover:bg-surface-muted disabled:opacity-50 sm:self-auto"
                >
                  <RotateCw className="h-3.5 w-3.5" aria-hidden />
                  Retry
                </button>
              )}
            </div>
          )}
        </div>

        {done && (message.sourceType || message.verificationFailed || message.id) && (
          <div className="flex flex-col gap-1.5 px-1">
            {message.sourceType && <EvidenceCard sourceType={message.sourceType} citationCount={message.citationCount ?? 0} />}
            {message.verificationFailed && (
              <p className="flex items-start gap-1.5 text-xs text-warning">
                <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
                The self-check flagged parts of this answer as possibly unsupported by your curriculum.
              </p>
            )}
            {message.id && (
              <button
                type="button"
                onClick={() => onFlag(message.id as string)}
                disabled={message.flagged}
                className="inline-flex w-fit items-center gap-1.5 rounded-md text-xs text-tertiary hover:text-danger disabled:cursor-default disabled:text-danger"
              >
                <Flag className="h-3 w-3" aria-hidden />
                {message.flagged ? "Flagged for teacher review" : "Flag this response"}
              </button>
            )}
          </div>
        )}

        {message.misconceptionResolved && (
          <div role="status" className="flex items-start gap-3 rounded-xl border border-success/35 bg-success/8 px-4 py-3 text-sm">
            <PartyPopper className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
            <div>
              <p className="font-semibold text-success">Nice work, {message.misconceptionResolved} is unlocked for quizzes again.</p>
              <p className="mt-0.5 text-secondary">You worked through the misconception. Try a quiz to lock in the progress.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
