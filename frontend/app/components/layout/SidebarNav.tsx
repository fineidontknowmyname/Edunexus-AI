"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { UserRole } from "../../lib/types";
import { cn } from "../../lib/cn";
import { isActive, navFor } from "./nav";

export function SidebarNav({
  role,
  onNavigate,
}: {
  role: UserRole | null;
  onNavigate?: () => void;
  isDrawer?: boolean;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const pathname = usePathname();
  const items = navFor(role);

  return (
    <nav aria-label="Mobile navigation" className="flex flex-col py-3">
      <div className="px-5 py-2 font-mono text-[9px] uppercase tracking-[0.1em] text-red border-b border-line mb-2">
        [ NAVIGATION ]
      </div>
      <div className="divide-y divide-line/40">
        {items.map((item, idx) => {
          const active = isActive(pathname, item);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center justify-between px-5 py-3.5 font-mono text-xs uppercase tracking-[0.1em] transition-colors",
                active
                  ? "text-red bg-surface2 font-medium"
                  : "text-muted hover:text-red hover:bg-surface2/60"
              )}
            >
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-muted">{String(idx + 1).padStart(2, "0")} /</span>
                <span>{item.label}</span>
              </div>
              <span className="text-muted text-[10px]">↗</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
