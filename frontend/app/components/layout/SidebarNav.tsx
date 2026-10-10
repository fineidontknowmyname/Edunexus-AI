"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { UserRound } from "lucide-react";
import type { UserRole } from "../../lib/types";
import { cn } from "../../lib/cn";
import { isActive, navFor } from "./nav";

export function SidebarNav({ role, onNavigate }: { role: UserRole | null; onNavigate?: () => void }) {
  const pathname = usePathname();
  const items = navFor(role);

  const linkClass = (active: boolean) =>
    cn(
      "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
      active ? "bg-accent-secondary/10 text-accent-secondary" : "text-secondary hover:bg-surface-muted hover:text-primary"
    );

  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-1 p-3">
      <p className="px-3 pb-2 pt-1 text-[0.6875rem] font-semibold uppercase tracking-wider text-tertiary">
        {role === "educator" ? "Teaching" : "Learning"}
      </p>
      {items.map((item) => {
        const active = isActive(pathname, item);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={linkClass(active)}
          >
            {active && <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-accent-secondary" aria-hidden />}
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            {item.label}
          </Link>
        );
      })}
      <div className="mt-auto border-t border-subtle pt-2">
        <Link
          href="/profile"
          onClick={onNavigate}
          aria-current={pathname === "/profile" ? "page" : undefined}
          className={linkClass(pathname === "/profile")}
        >
          <UserRound className="h-4 w-4 shrink-0" aria-hidden />
          Profile
        </Link>
      </div>
    </nav>
  );
}
