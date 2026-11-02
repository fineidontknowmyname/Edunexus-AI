import { AlertTriangle, Flag, RotateCw, Sparkles } from "lucide-react";
import type { ChatMessageUI } from "../../lib/types";
import { cn } from "../../lib/cn";
import { EvidenceCard } from "./EvidenceCard";
import { MarkdownMessage } from "./MarkdownMessage";

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1.5 py-1.5" role="status">
      <span className="sr-only">Tutor is thinking</span>
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-red [animation-delay:-0.3s]" aria-hidden />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-red [animation-delay:-0.15s]" aria-hidden />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-red" aria-hidden />
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
  onFlag?: (messageId: string) => void;
  onRetry: (messageKey: string) => void;
  retryDisabled: boolean;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] sm:max-w-[75%] whitespace-pre-wrap break-words rounded-[3px] bg-ink text-bg px-4.5 py-3 font-sans text-sm leading-relaxed select-text">
          {message.content}
        </div>
      </div>
    );
  }

  const done = !message.streaming && !message.failed;

  return (
    <div className="flex gap-3.5">
      <span
        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[2px] border border-line bg-surface2 text-red font-serif text-sm"
        aria-hidden
      >
        <Sparkles className="h-3.5 w-3.5" />
      </span>
      <div className="flex min-w-0 max-w-full flex-1 flex-col gap-2 sm:max-w-[85%]">
        <div
          className={cn(
            "rounded-[3px] border bg-surface p-5 transition-colors",
            message.failed ? "border-red/40 bg-red/5" : "border-line"
          )}
          aria-busy={message.streaming || undefined}
        >
          {message.content ? (
            <>
              <MarkdownMessage content={message.content} />
              {message.streaming && (
                <span className="mt-2.5 inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wider text-muted" role="status">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red" aria-hidden />
                  Generating grounded response…
                </span>
              )}
            </>
          ) : message.streaming ? (
            <TypingDots />
          ) : null}

          {message.failed && (
            <div
              role="alert"
              className={cn("flex flex-col gap-2 font-mono text-[10px] sm:flex-row sm:items-center sm:justify-between", message.content && "mt-3 border-t border-line pt-3")}
            >
              <span className="flex items-start gap-2 text-red">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                <span>{message.errorDetail ?? "Something went wrong."}</span>
              </span>
              {message.retryMessage && (
                <button
                  type="button"
                  onClick={() => onRetry(message.key)}
                  disabled={retryDisabled}
                  className="inline-flex h-7 shrink-0 items-center gap-1.5 self-start rounded-full border border-control-line bg-surface px-3 font-mono text-[9px] uppercase tracking-wider text-ink hover:border-red hover:text-red sm:self-auto cursor-pointer"
                >
                  <RotateCw className="h-3 w-3" aria-hidden />
                  Retry
                </button>
              )}
              {done && onFlag && message.id && (
                <button
                  type="button"
                  onClick={() => onFlag(message.id!)}
                  className="inline-flex h-7 shrink-0 items-center gap-1 self-start rounded-full border border-control-line bg-surface px-2.5 font-mono text-[9px] uppercase tracking-wider text-muted hover:border-red hover:text-red transition-colors cursor-pointer"
                  title="Flag response"
                >
                  <Flag className="h-3 w-3" aria-hidden />
                  Flag
                </button>
              )}
            </div>
          )}
        </div>

        {done && (message.sourceType || message.verificationFailed || message.id) && (
          <div className="flex flex-col gap-1.5 px-1 font-mono text-[9px] uppercase tracking-wider">
            {message.sourceType && <EvidenceCard sourceType={message.sourceType} citationCount={message.citationCount ?? 0} />}
            {message.verificationFailed && (
              <p className="flex items-start gap-1.5 text-warning">
                <AlertTriangle className="mt-px h-3 w-3 shrink-0" aria-hidden />
                Syllabus citation could not be confirmed against courseware.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
