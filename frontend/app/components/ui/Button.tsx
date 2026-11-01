import Link from "next/link";
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/cn";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "outline" | "ghost" | "danger" | "accent" | "filter";
export type ButtonSize = "sm" | "md" | "lg" | "icon";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-ink text-bg border-0 rounded-full hover:bg-red hover:-translate-y-0.5 transition-[transform,background] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] shadow-none",
  accent:
    "bg-ink text-bg border-0 rounded-full hover:bg-red hover:-translate-y-0.5 transition-[transform,background] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
  secondary:
    "bg-transparent text-ink border border-line rounded-full hover:border-red hover:text-red transition-all duration-250",
  outline:
    "bg-transparent text-ink border border-line rounded-full hover:border-red hover:text-red transition-all duration-250",
  ghost:
    "bg-transparent text-muted rounded-full hover:text-red transition-colors duration-200",
  danger:
    "bg-transparent text-red border border-red/60 rounded-full hover:bg-red hover:text-white transition-all duration-250",
  filter:
    "bg-transparent text-ink border border-line rounded-full text-[9px] hover:bg-ink hover:text-bg hover:border-ink transition-all duration-250",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[9px] gap-1.5",
  md: "h-[38px] px-[18px] text-[10px] gap-2",
  lg: "h-11 px-6 text-[11px] gap-2.5",
  icon: "h-[36px] w-[36px] p-0 justify-center rounded-full border border-line bg-transparent hover:border-red hover:rotate-12 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]",
};

export function buttonClasses({
  variant = "primary",
  size = "md",
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
} = {}) {
  return cn(
    "inline-flex items-center justify-center font-mono uppercase tracking-[0.1em] whitespace-nowrap select-none disabled:opacity-40 disabled:cursor-not-allowed disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red cursor-pointer",
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    className
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  disabled,
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={buttonClasses({ variant, size, className })}
      {...rest}
    >
      {loading ? <Spinner className="h-3.5 w-3.5" /> : icon}
      {children}
    </button>
  );
}

interface LinkButtonProps extends AnchorHTMLAttributes<HTMLAnchorElement> {
  href: string;
  children?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: ReactNode;
}

export function ButtonLink({ href, children, variant = "primary", size = "md", icon, className, ...rest }: LinkButtonProps) {
  return (
    <Link href={href} className={buttonClasses({ variant, size, className })} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

export const LinkButton = ButtonLink;
