import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { cn } from "../../lib/cn";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  icon,
  back,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  icon?: ReactNode;
  back?: { href: string; label: string };
  className?: string;
}) {
  const eyebrowText = typeof eyebrow === "string"
    ? eyebrow.replace(/^\s*\[\s*(.*?)\s*\]\s*$/, "$1")
    : eyebrow;

  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between pb-6 mb-6 border-b border-line", className)}>
      <div className="flex items-start gap-4 min-w-0">
        {icon && (
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center border border-line bg-surface2 text-red font-serif text-xl"
            aria-hidden
          >
            {icon}
          </div>
        )}
        <div className="min-w-0">
          {back && (
            <Link
              href={back.href}
              className="mb-2 inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted hover:text-red transition-colors"
            >
              <ArrowLeft className="h-3 w-3" aria-hidden />
              {back.label}
            </Link>
          )}
          {eyebrowText && (
            <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.1em] text-red">
              [ {eyebrowText} ]
            </div>
          )}
          <h1 className="font-serif text-3xl sm:text-4xl text-ink leading-none tracking-tight break-words">
            {title}
          </h1>
          {description && (
            <p className="mt-2 max-w-2xl font-sans text-xs sm:text-sm text-muted leading-relaxed">
              {description}
            </p>
          )}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:justify-end shrink-0">{actions}</div>}
    </header>
  );
}

export function PageContainer({
  children,
  width = "default",
  className,
}: {
  children: ReactNode;
  width?: "narrow" | "default" | "wide";
  className?: string;
}) {
  const max = width === "narrow" ? "max-w-4xl" : "max-w-[1480px]";
  return <div className={cn("mx-auto flex w-full flex-col gap-6", max, className)}>{children}</div>;
}
