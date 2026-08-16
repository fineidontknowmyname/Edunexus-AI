"use client";

import { ROLE_COOKIE, TOKEN_COOKIE, TOKEN_MAX_AGE_SECONDS } from "./constants";
import type { UserRole } from "./types";

function setCookie(name: string, value: string, maxAgeSeconds: number) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; samesite=lax`;
}

function getCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

function clearCookie(name: string) {
  document.cookie = `${name}=; path=/; max-age=0`;
}

export function storeSession(token: string, role: UserRole) {
  setCookie(TOKEN_COOKIE, token, TOKEN_MAX_AGE_SECONDS);
  setCookie(ROLE_COOKIE, role, TOKEN_MAX_AGE_SECONDS);
}

export function getToken(): string | null {
  return getCookie(TOKEN_COOKIE);
}

export function getRole(): UserRole | null {
  return getCookie(ROLE_COOKIE) as UserRole | null;
}

export function clearSession() {
  clearCookie(TOKEN_COOKIE);
  clearCookie(ROLE_COOKIE);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}
