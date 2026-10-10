import Link from "next/link";
import { cn } from "../../lib/cn";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-lg bg-accent-primary text-sm font-bold text-inverse",
        className
      )}
      aria-hidden
    >
      E
    </span>
  );
}

export function Logo({ href }: { href?: string }) {
  const content = (
    <>
      <LogoMark />
      <span className="text-[0.9375rem] font-semibold tracking-tight text-primary">
        EduNexus <span className="text-accent-secondary">AI</span>
      </span>
    </>
  );
  if (!href) return <span className="flex items-center gap-2.5">{content}</span>;
  return (
    <Link href={href} className="flex items-center gap-2.5 rounded-lg" aria-label="EduNexus AI home">
      {content}
    </Link>
  );
}
