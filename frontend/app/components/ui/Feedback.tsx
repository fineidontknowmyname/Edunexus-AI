import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, RotateCw, X, XCircle } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "./Button";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-[2px] bg-surface2", className)} aria-hidden />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3", i === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonCard({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("bg-surface border border-line rounded-[2px] p-6", className)} aria-hidden>
      <Skeleton className="h-4 w-1/3 mb-4" />
      <SkeletonText lines={lines} />
    </div>
  );
}

export function PageSkeleton({ cards = 3 }: { cards?: number }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-6">
      <span className="sr-only">Loading…</span>
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {Array.from({ length: cards }).map((_, i) => (
          <SkeletonCard key={i} lines={i === 0 ? 4 : 3} />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  compact = false,
  bracket = "EMPTY STATE",
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
  bracket?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center rounded-[2px] border border-dashed border-line bg-surface2/30",
        compact ? "px-4 py-8" : "px-6 py-14",
        className
      )}
    >
      {bracket && (
        <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
          [ {bracket} ]
        </span>
      )}
      {icon && (
        <span className="mb-3 flex h-10 w-10 items-center justify-center border border-line bg-surface2 text-muted" aria-hidden>
          {icon}
        </span>
      )}
      <h3 className="font-serif text-2xl text-ink leading-tight">{title}</h3>
      {description && <p className="mt-2 max-w-md font-sans text-xs sm:text-sm text-muted leading-relaxed">{description}</p>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string | null;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center text-center rounded-[2px] border border-red/40 bg-red/5 px-6 py-10",
        className
      )}
    >
      <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-2">
        [ SYSTEM ALERT ]
      </span>
      <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-red/30 bg-red/10 text-red" aria-hidden>
        <AlertTriangle className="h-5 w-5" />
      </span>
      <h3 className="font-serif text-2xl text-ink">{title}</h3>
      {message && <p className="mt-2 max-w-md font-sans text-xs sm:text-sm text-muted">{message}</p>}
      {onRetry && (
        <div className="mt-5">
          <Button variant="outline" size="sm" onClick={onRetry} icon={<RotateCw className="h-3.5 w-3.5" />}>
            Try again
          </Button>
        </div>
      )}
    </div>
  );
}

type AlertTone = "info" | "success" | "warning" | "danger";

const ALERT_STYLES: Record<AlertTone, { box: string; icon: ReactNode }> = {
  info: { box: "border-line bg-surface2/50 text-ink", icon: <Info className="h-4 w-4 text-muted" /> },
  success: { box: "border-green/40 bg-green/5 text-ink", icon: <CheckCircle2 className="h-4 w-4 text-green" /> },
  warning: { box: "border-warning/40 bg-warning/5 text-ink", icon: <AlertTriangle className="h-4 w-4 text-warning" /> },
  danger: { box: "border-red/40 bg-red/5 text-ink", icon: <XCircle className="h-4 w-4 text-red" /> },
};

export function Alert({
  tone = "info",
  title,
  children,
  action,
  onDismiss,
  className,
}: {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
  className?: string;
}) {
  const style = ALERT_STYLES[tone];
  return (
    <div
      role={tone === "danger" || tone === "warning" ? "alert" : "status"}
      className={cn("flex items-start gap-3 rounded-[2px] border px-4 py-3 text-xs sm:text-sm", style.box, className)}
    >
      <span className="mt-0.5 shrink-0" aria-hidden>
        {style.icon}
      </span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-mono text-[10px] uppercase tracking-[0.08em] font-semibold text-ink">{title}</p>}
        {children && <div className={cn("text-muted mt-1 leading-relaxed", Boolean(title) && "mt-1")}>{children}</div>}
        {action && <div className="mt-2.5">{action}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="rounded-full p-1 text-muted hover:text-red transition-colors"
        >
          <X className="h-3.5 w-3.5" aria-hidden />
        </button>
      )}
    </div>
  );
}
