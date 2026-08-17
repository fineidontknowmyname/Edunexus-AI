import type { ChatMessageUI } from "../../lib/types";
import { EvidenceCard } from "./EvidenceCard";

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
          className={`px-4 py-2 rounded-lg text-sm whitespace-pre-wrap ${
            isUser ? "bg-blue-600 text-white" : "bg-white border border-gray-200 text-gray-900"
          }`}
        >
          {message.content}
          {!message.content && message.streaming && (
            <span className="inline-flex gap-1 items-center">
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" />
            </span>
          )}
        </div>

        {!isUser && message.sourceType && (
          <EvidenceCard sourceType={message.sourceType} citationCount={message.citationCount ?? 0} />
        )}

        {!isUser && message.id && !message.streaming && (
          <button
            onClick={() => onFlag(message.id!)}
            disabled={message.flagged}
            className="mt-1 text-xs text-gray-400 hover:text-red-600 disabled:text-red-600 disabled:cursor-default"
          >
            {message.flagged ? "Flagged for teacher review" : "Flag this response"}
          </button>
        )}
      </div>
    </div>
  );
}
