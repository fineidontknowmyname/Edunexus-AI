"use client";

import { API_URL, CSRF_HEADER } from "../constants";
import { getCsrfToken } from "../auth";
import { errorFromResponse, redirectToLogin, refreshSession } from "../api";
import type { SessionMode, SourceType } from "../types";

export interface SSETokenEvent {
  type: "token";
  content?: string;
}

export interface SSEDoneEvent {
  type: "done";
  session_id?: string;
  message_id?: string;
  source_type?: SourceType;
  cached?: boolean;
  citations?: string[];
  verification_failed?: boolean;
  learning_tag?: string | null;
  misconception_resolved?: string | null;
}

export interface SSEErrorEvent {
  type: "error";
  detail?: string;
}

export type SSEEvent = SSETokenEvent | SSEDoneEvent | SSEErrorEvent;

export interface ChatQueryPayload {
  session_id?: string;
  class_id?: string;
  message: string;
  mode: SessionMode;
  topic?: string;
}

function postQuery(payload: ChatQueryPayload, signal?: AbortSignal): Promise<Response> {
  const csrfToken = getCsrfToken();
  return fetch(`${API_URL}/chat/query`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(csrfToken ? { [CSRF_HEADER]: csrfToken } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  });
}

function parseEvent(block: string): SSEEvent | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n")
    .trim();
  if (!data) return null;
  try {
    return JSON.parse(data) as SSEEvent;
  } catch {
    return null;
  }
}

export async function* streamChatQuery(payload: ChatQueryPayload, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
  const csrfAtRequest = getCsrfToken();
  let response = await postQuery(payload, signal);

  if (response.status === 401) {
    const refreshed = await refreshSession(csrfAtRequest);
    if (!refreshed) {
      redirectToLogin();
      yield { type: "error", detail: "Your session has expired. Please sign in again." };
      return;
    }
    response = await postQuery(payload, signal);
    if (response.status === 401) {
      redirectToLogin();
      yield { type: "error", detail: "Your session has expired. Please sign in again." };
      return;
    }
  }

  if (!response.ok || !response.body) {
    const err = await errorFromResponse(response);
    yield { type: "error", detail: err.message };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const event = parseEvent(part);
      if (event) yield event;
    }
  }

  buffer += decoder.decode();
  const trailing = parseEvent(buffer);
  if (trailing) yield trailing;
}
