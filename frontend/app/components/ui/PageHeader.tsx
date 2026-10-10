import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { cn } from "../../lib/cn";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  back,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  back?: { href: string; label: string };
  className?: string;
}) {
  return (
    <header className={cn("flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="min-w-0">
        {back && (
          <Link
            href={back.href}
            className="mb-2 inline-flex items-center gap-1.5 rounded-md text-sm font-medium text-tertiary hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            {back.label}
          </Link>
        )}
        {eyebrow && <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-accent-secondary">{eyebrow}</p>}
        <h1 className="text-2xl font-semibold tracking-tight text-primary sm:text-[1.75rem] sm:leading-9 break-words">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-sm text-tertiary sm:text-[0.9375rem]">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:justify-end">{actions}</div>}
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
  const max = width === "narrow" ? "max-w-3xl" : width === "wide" ? "max-w-7xl" : "max-w-5xl";
  return <div className={cn("mx-auto flex w-full flex-col gap-6", max, className)}>{children}</div>;
}
