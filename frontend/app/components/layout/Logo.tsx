import Link from "next/link";
import { cn } from "../../lib/cn";

export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("font-serif text-[28px] sm:text-[30px] tracking-[-1px] text-ink", className)}>
      EduNexus.
    </span>
  );
}

export function Logo({ href }: { href?: string }) {
  const content = (
    <span className="brand select-none">
      <span className="font-serif text-[28px] sm:text-[30px] tracking-[-1px] text-ink">
        EduNexus.
      </span>
      <small className="hidden sm:inline font-mono text-[10px] tracking-[0.12em] text-muted uppercase">
        AI / LEARNING SYSTEM
      </small>
    </span>
  );

  if (!href) return content;

  return (
    <Link
      href={href}
      className="inline-flex items-baseline no-underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red"
      aria-label="EduNexus AI Home"
    >
      {content}
    </Link>
  );
}
