"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, LogOut, Moon, Sun, UserRound } from "lucide-react";
import type { User } from "../../lib/types";
import { useTheme } from "../../lib/hooks/useTheme";
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
  return (
    <span
      className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-secondary/15 text-xs font-semibold text-accent-secondary",
        className
      )}
      aria-hidden
    >
      {initials(name) || <UserRound className="h-4 w-4" />}
    </span>
  );
}

export function UserMenu({ user, onLogout }: { user: User | null; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
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
    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm text-secondary hover:bg-surface-muted hover:text-primary focus:bg-surface-muted focus:text-primary focus:outline-none";

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
        className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-2 transition-colors hover:bg-surface-muted"
      >
        <Avatar name={user?.full_name} />
        <span className="hidden max-w-[10rem] truncate text-sm font-medium text-primary sm:inline">{user?.full_name ?? ""}</span>
        <ChevronDown className="h-4 w-4 text-tertiary" aria-hidden />
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Account"
          className="absolute right-0 z-40 mt-2 w-64 rounded-xl border border-subtle bg-surface-raised p-1.5 shadow-popover"
        >
          {user && (
            <div className="border-b border-subtle px-2.5 pb-2.5 pt-1.5 mb-1">
              <p className="truncate text-sm font-semibold text-primary">{user.full_name}</p>
              <p className="truncate text-xs text-tertiary">{user.email}</p>
              <p className="mt-1 text-[0.6875rem] font-semibold uppercase tracking-wider text-accent-secondary">{user.role}</p>
            </div>
          )}
          <Link href="/profile" role="menuitem" className={itemClass} onClick={() => setOpen(false)}>
            <UserRound className="h-4 w-4" aria-hidden />
            Profile &amp; settings
          </Link>
          <button type="button" role="menuitem" className={itemClass} onClick={toggleTheme}>
            {theme === "dark" ? <Sun className="h-4 w-4" aria-hidden /> : <Moon className="h-4 w-4" aria-hidden />}
            {theme === "dark" ? "Light theme" : "Dark theme"}
          </button>
          <div className="my-1 border-t border-subtle" />
          <button
            type="button"
            role="menuitem"
            className={itemClass}
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
