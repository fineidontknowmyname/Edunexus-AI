"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "../../lib/api";
import { streamChatQuery } from "../../lib/hooks/useSSE";
import type {
  ChatHistoryResponse,
  ChatMessageUI,
  ChatSessionSummary,
  ClassRow,
  SessionMode,
} from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { ChatInput } from "../../components/chat/ChatInput";
import { MessageBubble } from "../../components/chat/MessageBubble";

export default function ChatPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [classes, setClasses] = useState<ClassRow[] | null>(null);
  const [allClasses, setAllClasses] = useState<ClassRow[]>([]);
  const [joining, setJoining] = useState<string | null>(null);

  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [mode, setMode] = useState<SessionMode>("study");
  const [messages, setMessages] = useState<ChatMessageUI[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const autoSentRef = useRef<boolean>(false);

  useEffect(() => {
    apiFetch<ClassRow[]>("/classes/").then(setClasses);
  }, []);

  useEffect(() => {
    const topic = searchParams.get("topic");
    const urlMode = searchParams.get("mode");
    if (
      !autoSentRef.current &&
      urlMode === "socratic" &&
      topic &&
      !sessionId &&
      messages.length === 0 &&
      classes !== null &&
      classes.length > 0
    ) {
      autoSentRef.current = true;
      setMode("socratic");
      handleSend(topic);
      router.replace("/chat");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classes]);

  useEffect(() => {
    if (classes !== null && classes.length === 0) {
      apiFetch<ClassRow[]>("/classes/browse").then(setAllClasses);
    }
  }, [classes]);

  useEffect(() => {
    if (classes !== null && classes.length > 0) {
      refreshSessions();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classes]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function refreshSessions() {
    const rows = await apiFetch<ChatSessionSummary[]>("/chat/sessions");
    setSessions(rows);
  }

  async function handleJoin(classId: string) {
    setJoining(classId);
    try {
      await apiFetch(`/classes/${classId}/enroll`, { method: "POST" });
      const updated = await apiFetch<ClassRow[]>("/classes/");
      setClasses(updated);
    } finally {
      setJoining(null);
    }
  }

  function handleNewChat() {
    setSessionId(undefined);
    setMessages([]);
    setError(null);
  }

  async function handleLoadSession(id: string) {
    setLoadingHistory(true);
    setError(null);
    try {
      const detail = await apiFetch<ChatHistoryResponse>(`/chat/history?session_id=${id}`);
      setSessionId(detail.session_id);
      setMode(detail.mode);
      setMessages(
        detail.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          sourceType: m.source_type ?? undefined,
          flagged: m.flagged_by_student,
        }))
      );
    } finally {
      setLoadingHistory(false);
    }
  }

  async function handleSend(text: string) {
    setError(null);
    setStreaming(true);

    setMessages((prev) => [
      ...prev,
      { id: null, role: "user", content: text },
      { id: null, role: "assistant", content: "", streaming: true },
    ]);

    const classId = classes?.[0]?.id;
    const wasNewSession = !sessionId;

    try {
      for await (const event of streamChatQuery({ session_id: sessionId, class_id: classId, message: text, mode })) {
        if (event.type === "token") {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + (event.content ?? "") };
            return next;
          });
        } else if (event.type === "done") {
          setSessionId(event.session_id);
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = {
              ...last,
              id: event.message_id ?? null,
              streaming: false,
              sourceType: event.source_type,
              citationCount: event.citations?.length ?? 0,
              verificationFailed: event.verification_failed ?? false,
            };
            return next;
          });
          if (wasNewSession) refreshSessions();
        } else if (event.type === "error") {
          setError(event.detail ?? "Something went wrong.");
          setMessages((prev) => prev.slice(0, -1));
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Connection failed.");
    } finally {
      setStreaming(false);
    }
  }

  async function handleFlag(messageId: string) {
    await apiFetch(`/chat/messages/${messageId}/flag`, { method: "PATCH" });
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, flagged: true } : m)));
  }

  if (classes === null) {
    return <p className="text-sm text-tertiary">Loading…</p>;
  }

  if (classes.length === 0) {
    return (
      <div className="max-w-md mx-auto">
        <Card>
          <h2 className="font-semibold text-primary mb-2">Join a class to start chatting</h2>
          <p className="text-sm text-tertiary mb-4">You're not enrolled in any class yet.</p>
          <div className="flex flex-col gap-2">
            {allClasses.length === 0 ? (
              <p className="text-sm text-tertiary">No classes available yet.</p>
            ) : (
              allClasses.map((c) => (
                <div key={c.id} className="flex items-center justify-between border border-subtle rounded-md px-3 py-2">
                  <span className="text-sm text-primary">
                    {c.name} {c.subject ? `— ${c.subject}` : ""}
                  </span>
                  <Button variant="secondary" loading={joining === c.id} onClick={() => handleJoin(c.id)}>
                    Join
                  </Button>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col md:flex-row h-[calc(100vh-11rem)] md:h-[calc(100vh-8rem)] max-w-5xl mx-auto gap-4">
      <div className="hidden md:flex w-56 flex-col gap-2">
        <Button onClick={handleNewChat} className="w-full">
          New chat
        </Button>
        <div className="flex-1 overflow-y-auto flex flex-col gap-1">
          {sessions.length === 0 && <p className="text-xs text-tertiary px-2">No past sessions yet.</p>}
          {sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => handleLoadSession(s.session_id)}
              className={`text-left px-3 py-2 rounded-md text-xs ${
                s.session_id === sessionId ? "bg-accent-secondary/10 text-accent-secondary" : "text-secondary hover:bg-app"
              }`}
            >
              <div className="font-medium truncate">{s.preview || "New conversation"}</div>
              <div className="text-tertiary">{new Date(s.created_at).toLocaleDateString()} · {s.mode}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="md:hidden">
        <Button variant="secondary" onClick={handleNewChat} className="w-full">
          New chat
        </Button>
      </div>

      <div className="flex-1 flex flex-col md:border-l md:border-subtle md:pl-4 min-h-0">
        <div className="flex-1 overflow-y-auto flex flex-col gap-3 p-2">
          {loadingHistory && <p className="text-sm text-tertiary text-center">Loading conversation…</p>}
          {!loadingHistory && messages.length === 0 && (
            <p className="text-sm text-tertiary text-center mt-8">
              Ask a question about {classes[0].subject ?? classes[0].name}.
            </p>
          )}
          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} onFlag={handleFlag} />
          ))}
          {error && <p className="text-sm text-danger text-center">{error}</p>}
          <div ref={bottomRef} />
        </div>
        <ChatInput mode={mode} onModeChange={setMode} onSend={handleSend} disabled={streaming} />
      </div>
    </div>
  );
}
