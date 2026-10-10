"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowDown, Compass, History, MessageSquarePlus, Sparkles } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { streamChatQuery } from "../../lib/hooks/useSSE";
import { useApi } from "../../lib/hooks/useApi";
import {
  CHAT_HISTORY_LIMIT,
  CHAT_SESSIONS_PAGE_SIZE,
  CHAT_TOPIC_MAX_LENGTH,
} from "../../lib/constants";
import type {
  ChatHistoryResponse,
  ChatMessageUI,
  ChatSessionSummary,
  ClassRow,
  LearningPathResponse,
  SessionMode,
} from "../../lib/types";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Alert, Skeleton } from "../../components/ui/Feedback";
import { Drawer } from "../../components/ui/Modal";
import { ChatInput } from "../../components/chat/ChatInput";
import { MessageBubble } from "../../components/chat/MessageBubble";
import { SessionList } from "../../components/chat/SessionList";
import { StudentClassGate } from "../../components/layout/StudentClassGate";

let keyCounter = 0;
function newKey() {
  keyCounter += 1;
  return `m${Date.now().toString(36)}${keyCounter}`;
}

function guidedTopicFrom(params: URLSearchParams | null): string | null {
  if (!params || params.get("mode") !== "socratic") return null;
  const topic = params.get("topic")?.trim();
  return topic ? topic.slice(0, CHAT_TOPIC_MAX_LENGTH) : null;
}

function ChatFullBleed({ children }: { children: React.ReactNode }) {
  return (
    <div className="-mx-4 -my-6 flex h-[calc(100dvh-3.5rem)] min-h-[28rem] sm:-mx-6 lg:-mx-10 lg:-my-8">{children}</div>
  );
}

function ChatSkeleton() {
  return (
    <ChatFullBleed>
      <div className="hidden w-72 shrink-0 border-r border-subtle bg-surface p-3 lg:block">
        <Skeleton className="h-9 w-full" />
        <div className="mt-6 flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      </div>
      <div className="flex flex-1 flex-col p-6" role="status">
        <span className="sr-only">Loading chat…</span>
        <Skeleton className="h-6 w-48" />
        <div className="mt-auto">
          <Skeleton className="h-14 w-full rounded-2xl" />
        </div>
      </div>
    </ChatFullBleed>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<ChatSkeleton />}>
      <ChatPageInner />
    </Suspense>
  );
}

function ChatPageInner() {
  return (
    <StudentClassGate>
      {(activeClass, picker) => <ChatWorkspace key={activeClass.id} activeClass={activeClass} picker={picker} />}
    </StudentClassGate>
  );
}

function ChatWorkspace({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlTopic = guidedTopicFrom(searchParams);

  const [seenTopic, setSeenTopic] = useState<string | null>(urlTopic);
  const [guidedTopic, setGuidedTopic] = useState<string | null>(urlTopic);
  const [mode, setMode] = useState<SessionMode>(urlTopic ? "socratic" : "study");
  const [draft, setDraft] = useState(urlTopic ? `Help me work through ${urlTopic}` : "");
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessageUI[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyTruncated, setHistoryTruncated] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const [showJump, setShowJump] = useState(false);
  const sendingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  if (urlTopic !== seenTopic) {
    setSeenTopic(urlTopic);
    if (urlTopic) {
      setGuidedTopic(urlTopic);
      setMode("socratic");
      setDraft(`Help me work through ${urlTopic}`);
      setSessionId(undefined);
      setMessages([]);
      setHistoryTruncated(false);
    }
  }

  useEffect(() => {
    if (urlTopic) router.replace("/chat", { scroll: false });
  }, [urlTopic, router]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const pathQuery = useApi<LearningPathResponse>(`/progress/path?class_id=${activeClass.id}`);
  const suggestionTopics = (pathQuery.data?.path ?? [])
    .slice()
    .sort((a, b) => a.priority - b.priority)
    .slice(0, 3)
    .map((p) => p.topic);

  const fetchSessions = useCallback(async (offset: number) => {
    const rows = await apiFetch<ChatSessionSummary[]>(
      `/chat/sessions?limit=${CHAT_SESSIONS_PAGE_SIZE}&offset=${offset}`
    );
    const ignoredPaging = rows.length > CHAT_SESSIONS_PAGE_SIZE;
    return { rows, more: !ignoredPaging && rows.length === CHAT_SESSIONS_PAGE_SIZE };
  }, []);

  const loadFirstSessions = useCallback(() => {
    return fetchSessions(0).then(
      ({ rows, more }) => {
        setSessions(rows);
        setHasMore(more);
        setSessionsError(null);
        setSessionsLoading(false);
      },
      (err) => {
        setSessionsError(errorMessage(err, "Couldn't load your conversations."));
        setSessionsLoading(false);
      }
    );
  }, [fetchSessions]);

  useEffect(() => {
    loadFirstSessions();
  }, [loadFirstSessions]);

  async function handleLoadMore() {
    setLoadingMore(true);
    try {
      const { rows, more } = await fetchSessions(sessions.length);
      setSessions((prev) => {
        const seen = new Set(prev.map((s) => s.session_id));
        return [...prev, ...rows.filter((r) => !seen.has(r.session_id))];
      });
      setHasMore(more);
      setSessionsError(null);
    } catch (err) {
      setSessionsError(errorMessage(err, "Couldn't load more conversations."));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  function handleScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 96;
    stickToBottom.current = nearBottom;
    setShowJump(!nearBottom);
  }

  function jumpToLatest() {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = true;
    setShowJump(false);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }

  function handleNewChat() {
    setSessionId(undefined);
    setMessages([]);
    setNotice(null);
    setGuidedTopic(null);
    setHistoryTruncated(false);
    setHistoryOpen(false);
    stickToBottom.current = true;
  }

  async function handleLoadSession(id: string) {
    setHistoryOpen(false);
    if (id === sessionId) return;
    setHistoryLoading(true);
    setNotice(null);
    try {
      const detail = await apiFetch<ChatHistoryResponse>(
        `/chat/history?session_id=${id}&limit=${CHAT_HISTORY_LIMIT}`
      );
      setSessionId(detail.session_id);
      setMode(detail.mode === "exam_focus" ? "study" : detail.mode);
      setGuidedTopic(null);
      setHistoryTruncated(detail.messages.length >= CHAT_HISTORY_LIMIT);
      stickToBottom.current = true;
      setMessages(
        detail.messages.map((m) => ({
          key: m.id,
          id: m.id,
          role: m.role,
          content: m.content,
          sourceType: m.source_type ?? undefined,
          flagged: m.flagged_by_student,
          createdAt: m.created_at,
        }))
      );
    } catch (err) {
      setNotice(errorMessage(err, "Couldn't open that conversation."));
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleSend(text: string) {
    if (sendingRef.current) return;
    sendingRef.current = true;
    setNotice(null);
    setStreaming(true);
    stickToBottom.current = true;

    const assistantKey = newKey();
    setMessages((prev) => [
      ...prev,
      { key: newKey(), id: null, role: "user", content: text },
      { key: assistantKey, id: null, role: "assistant", content: "", streaming: true, retryMessage: text },
    ]);

    const update = (patch: (m: ChatMessageUI) => Partial<ChatMessageUI>) =>
      setMessages((prev) => prev.map((m) => (m.key === assistantKey ? { ...m, ...patch(m) } : m)));

    const controller = new AbortController();
    abortRef.current = controller;
    const wasNewSession = !sessionId;
    let finished = false;
    let failure: string | null = null;

    try {
      const stream = streamChatQuery(
        {
          session_id: sessionId,
          class_id: activeClass.id,
          message: text,
          mode,
          ...(guidedTopic ? { topic: guidedTopic } : {}),
        },
        controller.signal
      );
      for await (const event of stream) {
        if (event.type === "token") {
          const chunk = event.content ?? "";
          if (chunk) update((m) => ({ content: m.content + chunk }));
        } else if (event.type === "done") {
          finished = true;
          if (event.session_id) setSessionId(event.session_id);
          update(() => ({
            id: event.message_id ?? null,
            streaming: false,
            sourceType: event.source_type,
            citationCount: event.citations?.length ?? 0,
            verificationFailed: event.verification_failed ?? false,
            misconceptionResolved: event.misconception_resolved ?? null,
          }));
        } else if (event.type === "error") {
          failure = event.detail || "The tutor ran into a problem answering that.";
          break;
        }
      }
      if (!finished && !failure) failure = "The response was interrupted before it finished.";
    } catch (err) {
      if (controller.signal.aborted) return;
      failure = errorMessage(err, "Connection lost while the tutor was answering.");
    } finally {
      sendingRef.current = false;
      setStreaming(false);
    }

    if (failure) {
      const detail = failure;
      update(() => ({ streaming: false, failed: true, errorDetail: detail }));
    } else if (wasNewSession) {
      loadFirstSessions();
    }
  }

  function handleRetry(assistantKey: string) {
    if (sendingRef.current) return;
    const index = messages.findIndex((m) => m.key === assistantKey);
    const target = messages[index];
    if (!target?.retryMessage) return;
    const text = target.retryMessage;
    setMessages((prev) => {
      const i = prev.findIndex((m) => m.key === assistantKey);
      if (i === -1) return prev;
      const start = i > 0 && prev[i - 1].role === "user" ? i - 1 : i;
      return [...prev.slice(0, start), ...prev.slice(i + 1)];
    });
    handleSend(text);
  }

  async function handleFlag(messageId: string) {
    try {
      await apiFetch(`/chat/messages/${messageId}/flag`, { method: "PATCH" });
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, flagged: true } : m)));
    } catch (err) {
      setNotice(errorMessage(err, "Couldn't flag that response."));
    }
  }

  const subjectName = activeClass.subject ?? activeClass.name;
  const sessionListProps = {
    sessions,
    activeId: sessionId,
    loading: sessionsLoading,
    error: sessionsError,
    hasMore,
    loadingMore,
    disabled: streaming,
    onSelect: handleLoadSession,
    onNew: handleNewChat,
    onLoadMore: handleLoadMore,
    onRetry: () => {
      setSessionsLoading(true);
      loadFirstSessions();
    },
  };

  return (
    <ChatFullBleed>
      <aside className="hidden w-72 shrink-0 flex-col border-r border-subtle bg-surface lg:flex" aria-label="Conversations">
        <div className="px-3 pt-3 empty:hidden">{picker("w-full")}</div>
        <div className="min-h-0 flex-1">
          <SessionList {...sessionListProps} />
        </div>
      </aside>

      <section className="relative flex min-w-0 flex-1 flex-col" aria-label="Tutor chat">
        <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-subtle bg-surface/60 px-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setHistoryOpen(true)}
              aria-label="Show conversation history"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-secondary hover:bg-surface-muted hover:text-primary lg:hidden"
            >
              <History className="h-4 w-4" aria-hidden />
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold text-primary">{sessionId ? "Conversation" : "New conversation"}</h1>
              <p className="truncate text-xs text-tertiary">{activeClass.name}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {guidedTopic && (
              <Badge tone="blue" icon={<Compass className="h-3 w-3" aria-hidden />} className="max-w-[10rem] sm:max-w-xs">
                <span className="truncate">Guided: {guidedTopic}</span>
              </Badge>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={handleNewChat}
              disabled={streaming}
              icon={<MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />}
              className="lg:hidden"
            >
              New
            </Button>
          </div>
        </div>

        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="min-h-0 flex-1 overflow-y-auto"
          aria-live="polite"
          aria-relevant="additions"
        >
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 sm:px-6">
            {notice && (
              <Alert tone="danger" onDismiss={() => setNotice(null)}>
                {notice}
              </Alert>
            )}
            {guidedTopic && messages.length === 0 && (
              <Alert
                tone="info"
                title={`Guided session: ${guidedTopic}`}
                onDismiss={() => setGuidedTopic(null)}
              >
                The tutor will walk you through {guidedTopic} with questions rather than handing you the answer. Every message in this session stays focused on this topic.
              </Alert>
            )}
            {historyTruncated && (
              <p className="text-center text-xs text-tertiary">
                Showing the most recent {CHAT_HISTORY_LIMIT} messages. Earlier messages aren&apos;t shown.
              </p>
            )}
            {historyLoading ? (
              <div className="flex flex-col gap-5" role="status">
                <span className="sr-only">Loading conversation…</span>
                <Skeleton className="ml-auto h-10 w-2/3 rounded-2xl" />
                <Skeleton className="h-28 w-5/6 rounded-2xl" />
                <Skeleton className="ml-auto h-10 w-1/2 rounded-2xl" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-center sm:py-14">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-secondary/12 text-accent-secondary" aria-hidden>
                  <Sparkles className="h-6 w-6" />
                </span>
                <h2 className="mt-4 text-lg font-semibold text-primary">
                  {guidedTopic ? `Let's work through ${guidedTopic}` : `What would you like to learn in ${subjectName}?`}
                </h2>
                <p className="mt-1 max-w-md text-sm text-tertiary">
                  Answers come from your course materials first. Anything that isn&apos;t is clearly marked as general knowledge.
                </p>
                {!guidedTopic && suggestionTopics.length > 0 && (
                  <div className="mt-6 grid w-full max-w-xl gap-2 sm:grid-cols-3">
                    {suggestionTopics.map((topic) => (
                      <button
                        key={topic}
                        type="button"
                        onClick={() => setDraft(`Explain ${topic} in simple terms with an example.`)}
                        className="rounded-xl border border-subtle bg-surface px-3 py-2.5 text-left text-sm text-secondary shadow-card transition-colors hover:border-strong hover:text-primary"
                      >
                        <span className="block text-xs font-medium text-tertiary">Explain</span>
                        <span className="block truncate font-medium text-primary">{topic}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              messages.map((m) => (
                <MessageBubble key={m.key} message={m} onFlag={handleFlag} onRetry={handleRetry} retryDisabled={streaming} />
              ))
            )}
          </div>
        </div>

        {showJump && (
          <button
            type="button"
            onClick={jumpToLatest}
            className="absolute bottom-40 left-1/2 z-10 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-subtle bg-surface-raised px-3 py-1.5 text-xs font-medium text-primary shadow-popover"
          >
            <ArrowDown className="h-3.5 w-3.5" aria-hidden />
            Jump to latest
          </button>
        )}

        <div className="shrink-0 border-t border-subtle bg-surface/60 px-3 pb-3 pt-3 sm:px-6">
          <div className="mx-auto w-full max-w-3xl">
            <ChatInput
              mode={mode}
              onModeChange={setMode}
              value={draft}
              onChange={setDraft}
              onSend={handleSend}
              disabled={streaming}
              placeholder={guidedTopic ? `Ask about ${guidedTopic}…` : `Ask about ${subjectName}…`}
            />
          </div>
        </div>
      </section>

      <Drawer open={historyOpen} onClose={() => setHistoryOpen(false)} title="Conversations">
        <div className="flex h-full flex-col">
          <div className="px-3 pt-3 empty:hidden">{picker("w-full")}</div>
          <div className="min-h-0 flex-1">
            <SessionList {...sessionListProps} />
          </div>
        </div>
      </Drawer>
    </ChatFullBleed>
  );
}

