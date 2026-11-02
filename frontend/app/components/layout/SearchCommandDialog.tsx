"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import type { UserRole } from "../../lib/types";
import { navFor } from "./nav";

export function SearchCommandDialog({
  open,
  onClose,
  role,
}: {
  open: boolean;
  onClose: () => void;
  role: UserRole | null | undefined;
}) {
  const [query, setQuery] = useState("");
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const items = [
    ...navFor(role),
    { href: "/profile", label: "Profile & Settings", icon: null },
  ];

  const filtered = items.filter((item) =>
    item.label.toLowerCase().includes(query.trim().toLowerCase())
  );

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      setQuery("");
      inputRef.current?.focus();
    }, 10);
    return () => clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) {
          onClose();
        }
      }
      if (e.key === "Escape" && open) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Quick Navigator"
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 p-4 sm:pt-24"
    >
      <div
        className="fixed inset-0 bg-overlay backdrop-blur-[5px] transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="relative w-full max-w-lg rounded-[3px] border border-line bg-surface shadow-shadow overflow-hidden z-10 animate-[pageIn_0.35s_cubic-bezier(0.16,1,0.3,1)_both]">
        <div className="flex items-center gap-3 border-b border-line px-4 py-3 bg-surface2/30">
          <Search className="h-4 w-4 text-muted shrink-0" aria-hidden />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="SEARCH NAVIGATION ↵ (ESC TO EXIT)"
            className="w-full bg-transparent font-mono text-xs uppercase tracking-[0.08em] text-ink placeholder:text-muted focus:outline-none"
          />
          <kbd className="hidden sm:inline-flex h-5 items-center rounded border border-line bg-surface px-1.5 font-mono text-[9px] uppercase tracking-wider text-muted">
            ESC
          </kbd>
        </div>

        <div className="max-h-72 overflow-y-auto p-1">
          {filtered.length === 0 ? (
            <p className="p-6 text-center font-mono text-[10px] uppercase tracking-[0.08em] text-muted">
              NO MATCHING PAGES FOUND FOR &ldquo;{query}&rdquo;
            </p>
          ) : (
            <ul className="divide-y divide-line/40" role="listbox">
              {filtered.map((item, idx) => (
                <li key={item.href}>
                  <button
                    type="button"
                    onClick={() => {
                      router.push(item.href);
                      onClose();
                    }}
                    className="flex w-full items-center justify-between px-3 py-2.5 text-left font-mono text-[10px] uppercase tracking-[0.08em] text-ink hover:bg-ink hover:text-bg transition-colors group cursor-pointer"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-muted group-hover:text-inherit">
                        {String(idx + 1).padStart(2, "0")} /
                      </span>
                      <span className="font-medium group-hover:text-inherit">{item.label}</span>
                    </div>
                    <span className="text-muted group-hover:text-inherit">
                      JUMP ↗
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t border-line bg-surface2/40 px-4 py-2 font-mono text-[9px] uppercase tracking-[0.08em] text-muted flex items-center justify-between">
          <span>EDUNEXUS QUICK NAVIGATOR</span>
          <span className="flex items-center gap-1">
            <kbd className="font-mono text-[9px]">ENTER</kbd> TO SELECT
          </span>
        </div>
      </div>
    </div>
  );
}
