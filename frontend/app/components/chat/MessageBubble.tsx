import type { ChatMessageUI } from "../../lib/types";
import { EvidenceCard } from "./EvidenceCard";
import { MarkdownMessage } from "./MarkdownMessage";

export function MessageBubble({
  message,
  onFlag,
}: {
  message: ChatMessageUI;
  onFlag: (messageId: string) => void;
}) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[75%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`px-4 py-2 rounded-lg ${
            isUser
              ? "bg-accent-primary text-inverse text-sm whitespace-pre-wrap"
              : "bg-surface border border-subtle text-primary"
          }`}
        >
          {isUser ? message.content : <MarkdownMessage content={message.content} />}
          {!message.content && message.streaming && (
            <span className="inline-flex gap-1 items-center">
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-tertiary animate-bounce" />
            </span>
          )}
        </div>

        {!isUser && message.sourceType && (
          <EvidenceCard sourceType={message.sourceType} citationCount={message.citationCount ?? 0} />
        )}

        {!isUser && message.verificationFailed && !message.streaming && (
          <span className="mt-1 text-xs text-tertiary">
            ⚠ Self-check flagged parts of this as possibly unsupported by your curriculum.
          </span>
        )}

        {!isUser && message.id && !message.streaming && (
          <button
            onClick={() => onFlag(message.id!)}
            disabled={message.flagged}
            className="mt-1 text-xs text-tertiary hover:text-danger disabled:text-danger disabled:cursor-default"
          >
            {message.flagged ? "Flagged for teacher review" : "Flag this response"}
          </button>
        )}
      </div>
    </div>
  );
}
