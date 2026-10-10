"use client";

import { API_URL, CSRF_HEADER, REFRESH_LOCK_NAME } from "./constants";
import { clearSession, getCsrfToken, hardNavigate } from "./auth";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const NO_REFRESH_PATHS = new Set(["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"]);

const STATUS_FALLBACKS: Record<number, string> = {
  400: "That request could not be processed.",
  403: "You don't have permission to do that.",
  404: "We couldn't find what you were looking for.",
  409: "This was already submitted.",
  413: "That file is too large.",
  422: "Some of the information provided is invalid.",
  429: "You're doing that too often. Please wait a moment and try again.",
  500: "The server ran into a problem. Please try again.",
  502: "The server is unavailable right now. Please try again shortly.",
  503: "The server is starting up or busy. Please try again shortly.",
  504: "The server took too long to respond. Please try again.",
};

function fallbackFor(status: number): string {
  return STATUS_FALLBACKS[status] ?? (status >= 500 ? STATUS_FALLBACKS[500] : "Something went wrong. Please try again.");
}

function detailToText(detail: unknown): string | null {
  if (typeof detail === "string") return detail.trim() || null;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const msg = String((item as { msg: unknown }).msg);
          const loc = (item as { loc?: unknown[] }).loc;
          const field = Array.isArray(loc) ? loc.filter((p) => p !== "body").join(".") : "";
          return field ? `${field}: ${msg}` : msg;
        }
        return null;
      })
      .filter(Boolean);
    return parts.length > 0 ? parts.join("; ") : null;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return null;
}

function retryAfterSuffix(response: Response): string {
  const header = response.headers.get("Retry-After");
  const seconds = header ? Number(header) : NaN;
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  return ` Try again in ${Math.ceil(seconds)} second${Math.ceil(seconds) === 1 ? "" : "s"}.`;
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let message: string | null = null;
  try {
    const text = await response.text();
    if (text) {
      try {
        const body = JSON.parse(text) as { detail?: unknown };
        message = detailToText(body.detail ?? body);
      } catch {
        message = text.length < 300 && !text.trimStart().startsWith("<") ? text : null;
      }
    }
  } catch {}
  const base = message ?? fallbackFor(response.status);
  const suffix = response.status === 429 && !/try again in/i.test(base) ? retryAfterSuffix(response) : "";
  return new ApiError(response.status, `${base}${suffix}`);
}

export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  if (err instanceof ApiError) return err.message || fallback;
  if (err instanceof TypeError) return "Couldn't reach the server. Check your connection and try again.";
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

let refreshPromise: Promise<boolean> | null = null;

function postRefresh(): Promise<boolean> {
  return rawFetch("/auth/refresh", { method: "POST" })
    .then((res) => res.ok)
    .catch(() => false);
}

async function refreshAcrossTabs(csrfAtRequest: string | null): Promise<boolean> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (!locks || typeof locks.request !== "function") {
    return postRefresh();
  }
  return locks.request(REFRESH_LOCK_NAME, async () => {
    const current = getCsrfToken();
    if (current !== csrfAtRequest) {
      return current !== null;
    }
    return postRefresh();
  });
}

export function refreshSession(csrfAtRequest: string | null = getCsrfToken()): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = refreshAcrossTabs(csrfAtRequest)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export function redirectToLogin() {
  clearSession();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    hardNavigate("/login");
  }
}

function buildHeaders(method: string, headers: HeadersInit | undefined, jsonBody: boolean): Headers {
  const finalHeaders = new Headers(headers);
  if (jsonBody) finalHeaders.set("Content-Type", "application/json");
  if (MUTATING_METHODS.has(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) finalHeaders.set(CSRF_HEADER, csrfToken);
  }
  return finalHeaders;
}

export function rawFetch(path: string, options: RequestOptions): Promise<Response> {
  const { body, headers, ...rest } = options;
  const method = (options.method ?? "GET").toUpperCase();
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  return fetch(`${API_URL}${path}`, {
    ...rest,
    method,
    credentials: "include",
    headers: buildHeaders(method, headers, !isFormData && body !== undefined),
    body: isFormData ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}, _retried = false): Promise<T> {
  const csrfAtRequest = getCsrfToken();
  const response = await rawFetch(path, options);

  if (response.status === 401 && !_retried && !NO_REFRESH_PATHS.has(path)) {
    const refreshed = await refreshSession(csrfAtRequest);
    if (refreshed) {
      return apiFetch<T>(path, options, true);
    }
    redirectToLogin();
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
