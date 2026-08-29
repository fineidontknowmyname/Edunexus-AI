import { ReactNode } from "react";

type BadgeTone = "gray" | "blue" | "green" | "red" | "amber";

const TONE_CLASSES: Record<BadgeTone, string> = {
  gray: "bg-surface-muted text-secondary",
  blue: "bg-accent-secondary/15 text-accent-secondary",
  green: "bg-success/15 text-success",
  red: "bg-danger/15 text-danger",
  amber: "bg-warning/15 text-warning",
};

export function Badge({ children, tone = "gray" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}
