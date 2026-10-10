"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { Menu } from "lucide-react";
import type { UserRole } from "../../lib/types";
import { useAuth, useAuthActions, homeForRole } from "../../lib/hooks/useAuth";
import { Drawer } from "../ui/Modal";
import { Logo } from "./Logo";
import { SidebarNav } from "./SidebarNav";
import { UserMenu } from "./UserMenu";

export function AppShell({ role, children }: { role: UserRole | null; children: ReactNode }) {
  const { user } = useAuth();
  const { logout } = useAuthActions();
  const [navOpen, setNavOpen] = useState(false);
  const effectiveRole = user?.role ?? role;

  return (
    <div className="flex min-h-dvh flex-col bg-app">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary focus:shadow-popover"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center justify-between gap-3 border-b border-subtle bg-surface/90 px-3 backdrop-blur supports-[backdrop-filter]:bg-surface/80 sm:px-5">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setNavOpen(true)}
            aria-label="Open navigation"
            aria-expanded={navOpen}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-secondary hover:bg-surface-muted hover:text-primary md:hidden"
          >
            <Menu className="h-5 w-5" aria-hidden />
          </button>
          <Logo href={homeForRole(effectiveRole)} />
        </div>
        <UserMenu user={user} onLogout={logout} />
      </header>

      <div className="flex flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-subtle bg-surface md:block">
          <div className="sticky top-14 h-[calc(100dvh-3.5rem)]">
            <SidebarNav role={effectiveRole} />
          </div>
        </aside>
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 py-6 focus:outline-none sm:px-6 lg:px-10 lg:py-8">
          {children}
        </main>
      </div>

      <Drawer open={navOpen} onClose={() => setNavOpen(false)} title="Navigation">
        <SidebarNav role={effectiveRole} onNavigate={() => setNavOpen(false)} />
      </Drawer>
    </div>
  );
}
