"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { ClassRow } from "../types";

const STORAGE_KEY = "edunexus_active_class";
const CHANGE_EVENT = "edunexus-active-class-change";

function read(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function useActiveClass(classes: ClassRow[] | null): [ClassRow | null, (id: string) => void] {
  const stored = useSyncExternalStore(subscribe, read, () => null);
  const active = classes?.find((c) => c.id === stored) ?? classes?.[0] ?? null;

  const setActive = useCallback((id: string) => {
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {}
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return [active, setActive];
}
