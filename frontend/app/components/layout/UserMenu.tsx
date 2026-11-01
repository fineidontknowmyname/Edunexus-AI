"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { LogOut, UserRound } from "lucide-react";
import type { User } from "../../lib/types";
import { cn } from "../../lib/cn";

function initials(name: string | undefined): string {
  if (!name) return "";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function Avatar({ name, className }: { name?: string; className?: string }) {
  const init = initials(name);
  return (
    <span
      className={cn(
        "avatar select-none shrink-0",
        className
      )}
      aria-hidden
    >
      {init || "ED"}
    </span>
  );
}

export function UserMenu({ user, onLogout }: { user: User | null; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    menuRef.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();

    function handlePointer(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
        return;
      }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
      if (items.length === 0) return;
      e.preventDefault();
      const index = items.indexOf(document.activeElement as HTMLElement);
      const nextIndex = e.key === "ArrowDown" ? (index + 1) % items.length : (index - 1 + items.length) % items.length;
      items[nextIndex].focus();
    }
    document.addEventListener("pointerdown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const itemClass =
    "flex w-full items-center gap-2.5 rounded-[2px] px-3 py-2 text-left font-mono text-[10px] uppercase tracking-[0.08em] text-muted hover:bg-surface2 hover:text-red focus:bg-surface2 focus:text-red focus:outline-none transition-colors";

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={user ? `Account menu for ${user.full_name}` : "Account menu"}
        className="flex items-center gap-2 rounded-full p-0.5 transition-opacity hover:opacity-85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red"
      >
        <Avatar name={user?.full_name} />
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Account"
          className="absolute right-0 z-40 mt-2 w-64 rounded-[3px] border border-line bg-surface p-2 shadow-shadow animate-[pageIn_0.25s_cubic-bezier(0.16,1,0.3,1)_both]"
        >
          {user && (
            <div className="border-b border-line px-3 pb-3 pt-2 mb-1">
              <p className="truncate font-serif text-lg text-ink leading-tight">{user.full_name}</p>
              <p className="truncate font-mono text-[9px] text-muted mt-0.5">{user.email}</p>
              <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.1em] text-red">[ {user.role} ]</p>
            </div>
          )}
          <Link href="/profile" role="menuitem" className={itemClass} onClick={() => setOpen(false)}>
            <UserRound className="h-3.5 w-3.5" aria-hidden />
            01 / Profile &amp; Settings
          </Link>
          <div className="my-1 border-t border-line" />
          <button
            type="button"
            role="menuitem"
            className={itemClass}
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <LogOut className="h-3.5 w-3.5 text-red" aria-hidden />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
