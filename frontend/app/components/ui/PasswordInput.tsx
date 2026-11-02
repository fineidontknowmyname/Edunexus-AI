"use client";

import { useId, useState } from "react";
import type { InputHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "../../lib/cn";
import { controlClasses } from "./Input";

interface PasswordInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
  hint?: string;
  error?: string | null;
}

export function PasswordInput({ label, hint, error, id, className, ...rest }: PasswordInputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const [visible, setVisible] = useState(false);

  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <label htmlFor={inputId} className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type={visible ? "text" : "password"}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          className={cn(controlClasses, "h-10 pl-3 pr-10", error ? "border-red" : "border-control-line", className)}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center text-muted hover:text-red transition-colors"
        >
          {visible ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
        </button>
      </div>
      {error ? (
        <span id={`${inputId}-error`} className="font-mono text-[10px] text-red" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span id={`${inputId}-hint`} className="font-mono text-[10px] text-muted">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
