"use client";

import { useAuth, useAuthActions } from "../../lib/hooks/useAuth";
import { Button } from "../ui/Button";
import { ThemeToggle } from "../ui/ThemeToggle";

export function Navbar() {
  const { user } = useAuth();
  const { logout } = useAuthActions();

  return (
    <header className="h-14 border-b border-subtle bg-surface flex items-center justify-between px-6">
      <span className="font-semibold text-primary">EduNexus AI</span>
      <div className="flex items-center gap-4">
        {user && <span className="hidden sm:inline text-sm text-secondary">{user.full_name}</span>}
        <ThemeToggle />
        <Button variant="secondary" onClick={logout}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
