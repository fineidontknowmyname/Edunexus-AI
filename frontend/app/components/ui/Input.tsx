import { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({ label, error, id, className = "", ...rest }: InputProps) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-sm font-medium text-secondary">
          {label}
        </label>
      )}
      <input
        id={id}
        className={`px-3 py-2 border rounded-md text-sm bg-surface text-primary placeholder:text-tertiary focus:outline-none focus:ring-2 focus:ring-accent-secondary ${
          error ? "border-danger" : "border-strong"
        } ${className}`}
        {...rest}
      />
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}
