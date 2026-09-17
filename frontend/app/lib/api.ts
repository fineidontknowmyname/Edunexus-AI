"use client";

import { API_URL, CSRF_HEADER } from "./constants";
import { clearSession, getCsrfToken } from "./auth";

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
const NO_REFRESH_PATHS = new Set(["/auth/login", "/auth/register", "/auth/refresh"]);

let refreshPromise: Promise<boolean> | null = null;

function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = rawFetch("/auth/refresh", { method: "POST" })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

function rawFetch(path: string, options: RequestOptions): Promise<Response> {
  const { body, headers, ...rest } = options;
  const method = (options.method ?? "GET").toUpperCase();

  const finalHeaders = new Headers(headers);
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  if (!isFormData && body !== undefined) {
    finalHeaders.set("Content-Type", "application/json");
  }
  if (MUTATING_METHODS.has(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) finalHeaders.set(CSRF_HEADER, csrfToken);
  }

  return fetch(`${API_URL}${path}`, {
    ...rest,
    method,
    credentials: "include",
    headers: finalHeaders,
    body: isFormData ? (body as FormData) : body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}, _retried = false): Promise<T> {
  let response = await rawFetch(path, options);

  if (response.status === 401 && !_retried && !NO_REFRESH_PATHS.has(path)) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return apiFetch<T>(path, options, true);
    }
    clearSession();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Session expired.");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const errBody = await response.json();
      detail = errBody.detail ?? detail;
    } catch {}
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
