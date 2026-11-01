"use client";

import { useId } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export const controlClasses =
  "w-full rounded-[2px] border border-line bg-surface px-3 py-2.5 font-mono text-xs text-ink placeholder:text-muted transition-colors duration-200 focus:outline-none focus:border-red disabled:opacity-50 disabled:cursor-not-allowed";

interface FieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  srOnlyLabel?: boolean;
}

function FieldShell({
  id,
  label,
  hint,
  error,
  srOnlyLabel,
  className,
  children,
}: FieldProps & { id: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn("flex flex-col gap-1.5 min-w-0", className)}>
      {label && (
        <label htmlFor={id} className={cn("font-mono text-[9px] uppercase tracking-[0.1em] text-muted", srOnlyLabel && "sr-only")}>
          {label}
        </label>
      )}
      {children}
      {error ? (
        <span id={`${id}-error`} className="font-mono text-[10px] text-red" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span id={`${id}-hint`} className="font-mono text-[10px] text-muted">
          {hint}
        </span>
      ) : null}
    </div>
  );
}

function describedBy(id: string, error?: string | null, hint?: ReactNode) {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement>, FieldProps {
  wrapperClassName?: string;
}

export function Input({ label, hint, error, srOnlyLabel, id, className, wrapperClassName, ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error} srOnlyLabel={srOnlyLabel} className={wrapperClassName}>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, error, hint)}
        className={cn(controlClasses, "h-10", error ? "border-red" : "border-line", className)}
        {...rest}
      />
    </FieldShell>
  );
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement>, FieldProps {
  wrapperClassName?: string;
}

export function Select({ label, hint, error, srOnlyLabel, id, className, wrapperClassName, children, ...rest }: SelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <FieldShell id={selectId} label={label} hint={hint} error={error} srOnlyLabel={srOnlyLabel} className={wrapperClassName}>
      <div className="relative">
        <select
          id={selectId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(selectId, error, hint)}
          className={cn(controlClasses, "h-10 appearance-none pl-3 pr-9 truncate", error ? "border-red" : "border-line", className)}
          {...rest}
        >
          {children}
        </select>
        <svg
          aria-hidden
          viewBox="0 0 20 20"
          className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted"
          fill="currentColor"
        >
          <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.17l3.71-3.94a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z" />
        </svg>
      </div>
    </FieldShell>
  );
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement>, FieldProps {
  wrapperClassName?: string;
}

export function Textarea({ label, hint, error, srOnlyLabel, id, className, wrapperClassName, ...rest }: TextareaProps) {
  const autoId = useId();
  const textareaId = id ?? autoId;
  return (
    <FieldShell id={textareaId} label={label} hint={hint} error={error} srOnlyLabel={srOnlyLabel} className={wrapperClassName}>
      <textarea
        id={textareaId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(textareaId, error, hint)}
        className={cn(controlClasses, "min-h-[96px] py-2 resize-y", error ? "border-red" : "border-line", className)}
        {...rest}
      />
    </FieldShell>
  );
}
