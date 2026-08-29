"use client";

import { useTheme } from "../../lib/hooks/useTheme";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      aria-label="Toggle color theme"
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="w-8 h-8 flex items-center justify-center rounded-full border border-subtle text-secondary hover:bg-surface-muted transition-colors"
    >
      {theme === "dark" ? "☀" : "☾"}
    </button>
  );
}
