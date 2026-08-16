import { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: "primary" | "secondary" | "danger";
  loading?: boolean;
}

const VARIANT_CLASSES: Record<string, string> = {
  primary: "bg-blue-600 hover:bg-blue-700 text-white",
  secondary: "bg-gray-100 hover:bg-gray-200 text-gray-900",
  danger: "bg-red-600 hover:bg-red-700 text-white",
};

export function Button({
  children,
  variant = "primary",
  loading = false,
  disabled,
  className = "",
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`px-4 py-2 rounded-md font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {loading ? "Please wait…" : children}
    </button>
  );
}
