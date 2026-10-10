import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, RotateCw, X, XCircle } from "lucide-react";
import { cn } from "../../lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-muted", className)} aria-hidden />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn("h-3.5", i === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonCard({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn("bg-surface border border-subtle rounded-xl shadow-card p-5 sm:p-6", className)} aria-hidden>
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
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      {Array.from({ length: cards }).map((_, i) => (
        <SkeletonCard key={i} lines={i === 0 ? 4 : 3} />
      ))}
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
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-strong",
        compact ? "px-4 py-6" : "px-6 py-10",
        className
      )}
    >
      {icon && (
        <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-secondary" aria-hidden>
          {icon}
        </span>
      )}
      <p className="text-sm font-semibold text-primary">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-tertiary">{description}</p>}
      {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
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
        "flex flex-col items-center justify-center text-center rounded-xl border border-danger/30 bg-danger/5 px-6 py-8",
        className
      )}
    >
      <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-danger/10 text-danger" aria-hidden>
        <AlertTriangle className="h-5 w-5" />
      </span>
      <p className="text-sm font-semibold text-primary">{title}</p>
      {message && <p className="mt-1 max-w-md text-sm text-secondary">{message}</p>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg border border-strong bg-surface px-4 text-sm font-medium text-primary shadow-sm hover:bg-surface-muted"
        >
          <RotateCw className="h-4 w-4" aria-hidden />
          Try again
        </button>
      )}
    </div>
  );
}

type AlertTone = "info" | "success" | "warning" | "danger";

const ALERT_STYLES: Record<AlertTone, { box: string; icon: ReactNode }> = {
  info: { box: "border-info/30 bg-info/8 text-info", icon: <Info className="h-4 w-4" /> },
  success: { box: "border-success/30 bg-success/8 text-success", icon: <CheckCircle2 className="h-4 w-4" /> },
  warning: { box: "border-warning/35 bg-warning/10 text-warning", icon: <AlertTriangle className="h-4 w-4" /> },
  danger: { box: "border-danger/30 bg-danger/8 text-danger", icon: <XCircle className="h-4 w-4" /> },
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
      className={cn("flex items-start gap-3 rounded-lg border px-3.5 py-3 text-sm", style.box, className)}
    >
      <span className="mt-0.5 shrink-0" aria-hidden>
        {style.icon}
      </span>
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cn("text-secondary", Boolean(title) && "mt-0.5")}>{children}</div>}
        {action && <div className="mt-2">{action}</div>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-m-1 rounded-md p-1 text-tertiary hover:bg-surface-muted hover:text-primary"
        >
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
    </div>
  );
}
