"use client";

import { useAuth, useAuthActions } from "../../lib/hooks/useAuth";
import { Button } from "../ui/Button";

export function Navbar() {
  const { user } = useAuth();
  const { logout } = useAuthActions();

  return (
    <header className="h-14 border-b border-gray-200 bg-white flex items-center justify-between px-6">
      <span className="font-semibold text-gray-900">EduNexus AI</span>
      <div className="flex items-center gap-4">
        {user && <span className="text-sm text-gray-600">{user.full_name}</span>}
        <Button variant="secondary" onClick={logout}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
