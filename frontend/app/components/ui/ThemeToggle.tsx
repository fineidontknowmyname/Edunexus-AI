"use client";

import { useTheme } from "../../lib/hooks/useTheme";
import { cn } from "../../lib/cn";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={cn("icon-btn text-xs select-none", className)}
    >
      ◐
    </button>
  );
}
