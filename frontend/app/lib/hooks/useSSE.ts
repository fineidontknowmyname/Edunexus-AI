"use client";

import { API_URL, CSRF_HEADER } from "../constants";
import { getCsrfToken } from "../auth";
import type { SessionMode } from "../types";

export interface SSEEvent {
  type: "token" | "done" | "error";
  content?: string;
  session_id?: string;
  message_id?: string;
  source_type?: "curriculum" | "general_knowledge";
  cached?: boolean;
  citations?: string[];
  detail?: string;
  verification_failed?: boolean;
  learning_tag?: string | null;
}

export interface ChatQueryPayload {
  session_id?: string;
  class_id?: string;
  message: string;
  mode: SessionMode;
}

export async function* streamChatQuery(payload: ChatQueryPayload): AsyncGenerator<SSEEvent> {
  const csrfToken = getCsrfToken();
  const response = await fetch(`${API_URL}/chat/query`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(csrfToken ? { [CSRF_HEADER]: csrfToken } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    yield { type: "error", detail: text || response.statusText };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const jsonStr = line.slice(5).trim();
      try {
        yield JSON.parse(jsonStr) as SSEEvent;
      } catch {
        continue;
      }
    }
  }
}
