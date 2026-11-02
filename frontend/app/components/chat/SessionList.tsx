"use client";

import { MessageSquarePlus } from "lucide-react";
import type { ChatSessionSummary, SessionMode } from "../../lib/types";
import { cn } from "../../lib/cn";
import { formatRelative } from "../../lib/format";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Feedback";

const MODE_LABEL: Record<SessionMode, string> = {
  study: "Study",
  revision: "Revision",
  socratic: "Socratic",
  exam_focus: "Exam focus",
};

export function SessionList({
  sessions,
  activeId,
  loading,
  error,
  hasMore,
  loadingMore,
  disabled,
  onSelect,
  onNew,
  onLoadMore,
  onRetry,
}: {
  sessions: ChatSessionSummary[];
  activeId: string | undefined;
  loading: boolean;
  error: string | null;
  hasMore: boolean;
  loadingMore: boolean;
  disabled: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onLoadMore: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="p-3 border-b border-line">
        <Button onClick={onNew} disabled={disabled} variant="primary" size="sm" className="w-full" icon={<MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />}>
          New conversation
        </Button>
      </div>
      <p className="px-4 pb-1 pt-3 font-mono text-[9px] uppercase tracking-[0.1em] text-red">
        [ SESSIONS ]
      </p>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {loading && sessions.length === 0 ? (
          <div className="flex flex-col gap-2 p-2" aria-hidden>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-1.5 py-1">
                <Skeleton className="h-3.5 w-11/12" />
                <Skeleton className="h-3 w-1/2" />
              </div>
            ))}
          </div>
        ) : error && sessions.length === 0 ? (
          <div className="p-3 font-mono text-[10px] text-red" role="alert">
            <p>{error}</p>
            <button type="button" onClick={onRetry} className="mt-1 underline cursor-pointer">
              Try again
            </button>
          </div>
        ) : sessions.length === 0 ? (
          <p className="px-3 py-4 font-mono text-[9px] uppercase tracking-wider text-muted">No conversations yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 divide-y divide-line/30">
            {sessions.map((s) => {
              const active = s.session_id === activeId;
              return (
                <li key={s.session_id}>
                  <button
                    type="button"
                    onClick={() => onSelect(s.session_id)}
                    disabled={disabled}
                    aria-current={active ? "true" : undefined}
                    className={cn(
                      "w-full rounded-[2px] px-3 py-2.5 text-left transition-colors disabled:cursor-not-allowed cursor-pointer",
                      active ? "bg-surface2 text-red font-medium" : "hover:bg-surface2/60 text-ink"
                    )}
                  >
                    <span className="block truncate font-serif text-base leading-snug">
                      {s.preview || "New conversation"}
                    </span>
                    <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-wider text-muted">
                      {formatRelative(s.created_at)} · {MODE_LABEL[s.mode] ?? s.mode}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {hasMore && (
          <div className="px-1 pt-2">
            <Button variant="outline" size="sm" className="w-full" loading={loadingMore} onClick={onLoadMore}>
              Load more
            </Button>
          </div>
        )}
        {error && sessions.length > 0 && (
          <p className="px-3 pt-2 font-mono text-[10px] text-red" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
