import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
  href,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
  href?: string;
}) {
  const toneClass =
    tone === "danger" ? "text-danger" : tone === "warning" ? "text-warning" : tone === "success" ? "text-success" : "text-primary";
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-tertiary">{label}</span>
        {icon && (
          <span className="text-tertiary" aria-hidden>
            {icon}
          </span>
        )}
      </div>
      <div className={cn("mt-2 text-2xl font-semibold tabular-nums tracking-tight", toneClass)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-tertiary">{hint}</div>}
    </>
  );
  const classes = "block rounded-xl border border-subtle bg-surface p-4 shadow-card min-w-0";
  if (href) {
    return (
      <Link href={href} className={cn(classes, "transition-colors hover:border-strong")}>
        {body}
      </Link>
    );
  }
  return <div className={classes}>{body}</div>;
}

export function masteryTone(score: number): "green" | "amber" | "red" {
  if (score >= 0.7) return "green";
  if (score >= 0.4) return "amber";
  return "red";
}

export function ProgressBar({
  value,
  label,
  className,
  tone,
}: {
  value: number;
  label: string;
  className?: string;
  tone?: "green" | "amber" | "red" | "blue";
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const resolved = tone ?? masteryTone(value);
  const color =
    resolved === "green" ? "bg-success" : resolved === "amber" ? "bg-warning" : resolved === "red" ? "bg-danger" : "bg-accent-secondary";
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-surface-muted", className)}
    >
      <div className={cn("h-full rounded-full transition-[width] duration-500", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
