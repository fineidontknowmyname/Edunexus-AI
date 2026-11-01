"use client";

import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import { Menu, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { UserRole } from "../../lib/types";
import { useAuth, useAuthActions, homeForRole } from "../../lib/hooks/useAuth";
import { Drawer } from "../ui/Modal";
import { Logo } from "./Logo";
import { SidebarNav } from "./SidebarNav";
import { UserMenu } from "./UserMenu";
import { SearchCommandDialog } from "./SearchCommandDialog";
import { ThemeToggle } from "../ui/ThemeToggle";
import { cn } from "../../lib/cn";
import { isActive, navFor } from "./nav";

export function AppShell({ role, children }: { role: UserRole | null; children: ReactNode }) {
  const { user } = useAuth();
  const { logout } = useAuthActions();
  const pathname = usePathname();

  const [navOpen, setNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const effectiveRole = user?.role ?? role;
  const navItems = navFor(effectiveRole);

  useEffect(() => {
    function handleGlobalSearchKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    }
    window.addEventListener("keydown", handleGlobalSearchKey);
    return () => window.removeEventListener("keydown", handleGlobalSearchKey);
  }, []);

  return (
    <div className="min-h-dvh bg-bg text-ink flex flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-[2px] focus:bg-surface focus:px-4 focus:py-2 focus:font-mono focus:text-xs focus:text-red focus:shadow-shadow focus:outline-2 focus:outline-red"
      >
        Skip to content
      </a>

      {/* Reference Sticky Topbar */}
      <header className="topbar">
        <div className="top-inner shell">
          {/* Brand Wordmark Left */}
          <div className="flex items-center gap-4">
            <Logo href={homeForRole(effectiveRole)} />
          </div>

          {/* Center Desktop Numbered Mono Navigation */}
          <nav className="topnav hidden md:flex" aria-label="Main navigation">
            {navItems.map((item, idx) => {
              const active = isActive(pathname, item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "font-mono text-[10px] tracking-[0.1em] uppercase transition-colors duration-250 py-1",
                    active ? "text-red active" : "text-muted hover:text-red"
                  )}
                  aria-current={active ? "page" : undefined}
                >
                  {String(idx + 1).padStart(2, "0")} / {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Right Header Controls */}
          <div className="top-actions">
            {/* Search Trigger Button */}
            <button
              type="button"
              onClick={() => setSearchOpen(true)}
              className="icon-btn"
              aria-label="Search navigation (Cmd+K)"
              title="Search navigation (Cmd+K)"
            >
              <Search className="h-3.5 w-3.5" aria-hidden />
            </button>

            {/* Theme Toggle Button */}
            <ThemeToggle />

            {/* User Avatar & Menu */}
            <UserMenu user={user} onLogout={logout} />

            {/* Mobile Hamburger Menu Toggle (<850px) */}
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open mobile navigation"
              aria-expanded={navOpen}
              className="icon-btn md:hidden"
            >
              <Menu className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area with Route Entrance Transition */}
      <main
        id="main"
        tabIndex={-1}
        key={pathname}
        className="flex-1 w-full shell page-enter focus:outline-none px-[4.2vw] sm:px-[5vw] py-8"
      >
        {children}
      </main>

      {/* Reference Footer Strip */}
      <footer className="footer shell border-t border-line mt-auto">
        <span>EDUNEXUS AI / HIGHER EDUCATION LEARNING SYSTEM</span>
        <span>DESIGNED FOR FOCUS · 2026—27</span>
        <span className="text-right">ADAPTIVE CURRICULUM INTELLIGENCE</span>
      </footer>

      {/* Mobile Drawer Navigation */}
      <Drawer
        open={navOpen}
        onClose={() => setNavOpen(false)}
        title="Menu"
        category={effectiveRole ? effectiveRole.toUpperCase() : "EDUNEXUS"}
      >
        <SidebarNav role={effectiveRole} onNavigate={() => setNavOpen(false)} isDrawer />
      </Drawer>

      {/* Quick Search Dialog */}
      <SearchCommandDialog open={searchOpen} onClose={() => setSearchOpen(false)} role={effectiveRole} />
    </div>
  );
}
