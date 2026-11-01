import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { cn } from "../../lib/cn";

export function Card({
  children,
  className,
  padded = true,
  variant = "default",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
  variant?: "default" | "highlight";
  as?: "div" | "section" | "article" | "li";
}) {
  return (
    <Tag
      className={cn(
        "rounded-[3px] border border-line transition-all duration-300 min-w-0 relative",
        variant === "highlight"
          ? "bg-panel-dark text-panel-dark-text shadow-shadow"
          : "bg-surface hover:bg-surface2",
        padded && "p-6",
        className
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  icon,
  className,
  id,
  linkHref,
  showDot = false,
  bracket,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
  className?: string;
  id?: string;
  linkHref?: string;
  showDot?: boolean;
  bracket?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3 mb-4", className)}>
      <div className="flex items-start gap-3 min-w-0">
        {icon && (
          <span
            className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center border border-line bg-surface2 text-red font-serif text-lg"
            aria-hidden
          >
            {icon}
          </span>
        )}
        <div className="min-w-0">
          {bracket && (
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-1">
              [ {bracket} ]
            </div>
          )}
          <div className="flex items-center gap-2">
            {showDot && (
              <span className="dot" aria-hidden="true" />
            )}
            <h2 id={id} className="font-serif text-2xl sm:text-[1.75rem] text-ink leading-snug">
              {title}
            </h2>
          </div>
          {description && <p className="font-sans text-xs text-muted mt-1 leading-relaxed">{description}</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {actions}
        {linkHref && (
          <Link
            href={linkHref}
            className="flex h-7 w-7 items-center justify-center rounded-full border border-line text-muted hover:border-red hover:text-red transition-colors"
            aria-label="View details"
          >
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        )}
      </div>
    </div>
  );
}

export function CardTakeaway({ text, className }: { text: ReactNode; className?: string }) {
  if (!text) return null;
  return (
    <div className={cn("mt-4 pt-3 border-t border-line font-mono text-[10px] uppercase tracking-[0.08em] text-muted flex items-center gap-2", className)}>
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-red shrink-0" aria-hidden="true" />
      <span className="line-clamp-1">{text}</span>
    </div>
  );
}
