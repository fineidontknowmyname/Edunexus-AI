"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../api";
import { clearSession, getToken, storeSession } from "../auth";
import type { Token, User, UserRole } from "../types";

interface UseAuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

export function useAuth(): UseAuthState {
  const [state, setState] = useState<UseAuthState>({ user: null, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!getToken()) {
        if (!cancelled) setState({ user: null, loading: false, error: null });
        return;
      }
      try {
        const user = await apiFetch<User>("/auth/me");
        if (!cancelled) setState({ user, loading: false, error: null });
      } catch (err) {
        if (cancelled) return;
        setState({
          user: null,
          loading: false,
          error: err instanceof ApiError ? err.message : "Could not load profile",
        });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

export function useAuthActions() {
  async function login(email: string, password: string) {
    const { access_token } = await apiFetch<Token>("/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    const role = decodeRoleFromJwt(access_token);
    storeSession(access_token, role);
    window.location.href = role === "educator" ? "/upload" : "/chat";
  }

  async function register(email: string, password: string, full_name: string, role: UserRole) {
    await apiFetch<User>("/auth/register", {
      method: "POST",
      body: { email, password, full_name, role },
      auth: false,
    });
    await login(email, password);
  }

  function logout() {
    clearSession();
    window.location.href = "/login";
  }

  return { login, register, logout };
}

function decodeRoleFromJwt(token: string): UserRole {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return (payload.role as UserRole) ?? "student";
  } catch {
    return "student";
  }
}
