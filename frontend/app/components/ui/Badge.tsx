import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export type BadgeTone = "gray" | "blue" | "green" | "red" | "amber" | "info";

const TONE_CLASSES: Record<BadgeTone, string> = {
  gray: "bg-surface-muted text-secondary ring-strong/60",
  blue: "bg-accent-secondary/12 text-accent-secondary ring-accent-secondary/25",
  green: "bg-success/12 text-success ring-success/25",
  red: "bg-danger/12 text-danger ring-danger/25",
  amber: "bg-warning/14 text-warning ring-warning/30",
  info: "bg-info/12 text-info ring-info/25",
};

const DOT_CLASSES: Record<BadgeTone, string> = {
  gray: "bg-tertiary",
  blue: "bg-accent-secondary",
  green: "bg-success",
  red: "bg-danger",
  amber: "bg-warning",
  info: "bg-info",
};

export function Badge({
  children,
  tone = "gray",
  dot = false,
  icon,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
        TONE_CLASSES[tone],
        className
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full", DOT_CLASSES[tone])} aria-hidden />}
      {icon}
      {children}
    </span>
  );
}
