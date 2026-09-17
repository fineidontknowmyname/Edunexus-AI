"use client";

import { CSRF_COOKIE, ROLE_COOKIE } from "./constants";
import type { UserRole } from "./types";

function getCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

function clearCookie(name: string) {
  document.cookie = `${name}=; path=/; max-age=0`;
}

export function getRole(): UserRole | null {
  return getCookie(ROLE_COOKIE) as UserRole | null;
}

export function getCsrfToken(): string | null {
  return getCookie(CSRF_COOKIE);
}

export function clearSession() {
  clearCookie(ROLE_COOKIE);
  clearCookie(CSRF_COOKIE);
}

export function isAuthenticated(): boolean {
  return getRole() !== null;
}
