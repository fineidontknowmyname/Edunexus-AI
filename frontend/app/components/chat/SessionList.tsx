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
      <div className="p-3">
        <Button onClick={onNew} disabled={disabled} className="w-full" icon={<MessageSquarePlus className="h-4 w-4" aria-hidden />}>
          New chat
        </Button>
      </div>
      <p className="px-4 pb-1 pt-2 text-[0.6875rem] font-semibold uppercase tracking-wider text-tertiary">Recent</p>
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
          <div className="p-3 text-xs text-danger" role="alert">
            <p>{error}</p>
            <button type="button" onClick={onRetry} className="mt-1 font-medium underline">
              Try again
            </button>
          </div>
        ) : sessions.length === 0 ? (
          <p className="px-2 py-3 text-xs text-tertiary">No conversations yet. Ask your first question to get started.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
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
                      "w-full rounded-lg px-3 py-2 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60",
                      active ? "bg-accent-secondary/10" : "hover:bg-surface-muted"
                    )}
                  >
                    <span className={cn("block truncate text-sm", active ? "font-medium text-accent-secondary" : "text-primary")}>
                      {s.preview || "New conversation"}
                    </span>
                    <span className="mt-0.5 block text-xs text-tertiary">
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
            <Button variant="ghost" size="sm" className="w-full" loading={loadingMore} onClick={onLoadMore}>
              Load more
            </Button>
          </div>
        )}
        {error && sessions.length > 0 && (
          <p className="px-3 pt-2 text-xs text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
