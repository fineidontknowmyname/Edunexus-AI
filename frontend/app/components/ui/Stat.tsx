import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { cn } from "../../lib/cn";

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
  variant = "default",
  href,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: "default" | "warning" | "danger" | "success";
  variant?: "default" | "highlight";
  href?: string;
}) {
  const isHighlight = variant === "highlight";

  const toneClass = isHighlight
    ? "text-panel-dark-text"
    : tone === "danger"
    ? "text-red"
    : tone === "warning"
    ? "text-warning"
    : tone === "success"
    ? "text-green"
    : "text-ink";

  const body = (
    <div className="flex flex-col justify-between h-full">
      <div className="flex items-start justify-between gap-3">
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted">
          {label}
        </span>
        {icon && (
          <span className="flex h-8 w-8 items-center justify-center border border-line bg-surface2 text-red font-serif text-sm">
            {icon}
          </span>
        )}
        {href && !icon && (
          <span className="text-muted group-hover:text-red transition-colors">
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
          </span>
        )}
      </div>
      <div className="mt-3">
        <strong className={cn("block font-serif text-3xl sm:text-[40px] leading-none tracking-tight font-normal", toneClass)}>
          {value}
        </strong>
      </div>
      {hint && (
        <div className="mt-2 font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
          {hint}
        </div>
      )}
    </div>
  );

  const classes = cn(
    "group block p-5 sm:p-6 min-w-0 transition-colors duration-200 border border-line",
    isHighlight
      ? "bg-panel-dark text-panel-dark-text shadow-shadow"
      : "bg-surface hover:bg-surface2"
  );

  if (href) {
    return (
      <Link href={href} className={classes}>
        {body}
      </Link>
    );
  }
  return <div className={classes}>{body}</div>;
}

export function KpiStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid grid-cols-2 lg:grid-cols-4 border-b border-line", className)}>
      {children}
    </div>
  );
}

export function KpiCell({
  label,
  value,
  caption,
  tone = "default",
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  caption?: ReactNode;
  tone?: "default" | "red" | "green";
  className?: string;
}) {
  return (
    <div className={cn("p-5 sm:p-6 border-r border-b lg:border-b-0 border-line last:border-r-0 flex flex-col justify-between", className)}>
      <small className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted block">
        {label}
      </small>
      <strong className={cn("block font-serif text-3xl sm:text-[40px] my-2 font-normal leading-none", tone === "red" ? "text-red" : tone === "green" ? "text-green" : "text-ink")}>
        {value}
      </strong>
      {caption && (
        <small className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted block">
          {caption}
        </small>
      )}
    </div>
  );
}

export function FocusRow({
  icon,
  title,
  description,
  actions,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("focus-row", className)}>
      {icon && <div className="focus-icon">{icon}</div>}
      <div className="flex-1 min-w-0">
        <h4 className="font-serif text-xl text-ink leading-tight mb-1 truncate">{title}</h4>
        {description && <p className="font-sans text-xs text-muted truncate">{description}</p>}
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
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
  tone?: "green" | "amber" | "red" | "blue" | "teal";
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  const resolved = tone ?? masteryTone(value);
  const color = resolved === "green" ? "bg-green" : "bg-red";

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("progress-line", className)}
    >
      <span className={color} style={{ width: `${pct}%` }} />
    </div>
  );
}
