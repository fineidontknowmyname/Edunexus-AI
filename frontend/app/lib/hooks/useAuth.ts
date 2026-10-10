"use client";

import { useEffect, useState } from "react";
import { apiFetch, errorMessage } from "../api";
import { clearSession, hardNavigate, isAuthenticated } from "../auth";
import { EDUCATOR_HOME, STUDENT_HOME } from "../constants";
import type { LoginResponse, User, UserRole } from "../types";

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
      if (!isAuthenticated()) {
        if (!cancelled) setState({ user: null, loading: false, error: null });
        return;
      }
      try {
        const user = await apiFetch<User>("/auth/me");
        if (!cancelled) setState({ user, loading: false, error: null });
      } catch (err) {
        if (!cancelled) setState({ user: null, loading: false, error: errorMessage(err, "Could not load profile") });
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

export function homeForRole(role: UserRole | null | undefined): string {
  return role === "educator" ? EDUCATOR_HOME : STUDENT_HOME;
}

export function useAuthActions() {
  async function login(email: string, password: string) {
    const { user } = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    hardNavigate(homeForRole(user.role));
  }

  async function register(email: string, password: string, full_name: string, role: UserRole) {
    await apiFetch<User>("/auth/register", {
      method: "POST",
      body: { email, password, full_name, role },
    });
    await login(email, password);
  }

  async function logout() {
    await apiFetch("/auth/logout", { method: "POST" }).catch(() => {});
    clearSession();
    hardNavigate("/login");
  }

  return { login, register, logout };
}
