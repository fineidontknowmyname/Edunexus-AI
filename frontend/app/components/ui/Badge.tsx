import type { ReactNode } from "react";
import { CheckCircle2, HelpCircle, CircleDashed, TrendingUp } from "lucide-react";
import { cn } from "../../lib/cn";

export type BadgeTone = "gray" | "blue" | "teal" | "green" | "red" | "amber" | "info" | "purple" | "yellow";

const TONE_CLASSES: Record<BadgeTone, string> = {
  gray: "text-muted border-line bg-transparent",
  blue: "text-ink border-line bg-surface2",
  teal: "text-red border-line bg-transparent",
  green: "text-green border-line bg-transparent",
  red: "text-red border-red/40 bg-transparent",
  amber: "text-warning border-line bg-transparent",
  info: "text-muted border-line bg-transparent",
  purple: "text-muted border-line bg-transparent",
  yellow: "text-ink border-line bg-surface2",
};

const DOT_CLASSES: Record<BadgeTone, string> = {
  gray: "bg-muted",
  blue: "bg-red",
  teal: "bg-red",
  green: "bg-green",
  red: "bg-red",
  amber: "bg-warning",
  info: "bg-muted",
  purple: "bg-muted",
  yellow: "bg-ink",
};

export function Badge({
  children,
  tone = "gray",
  dot = false,
  pill = false,
  icon,
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  pill?: boolean;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.1em] border whitespace-nowrap",
        pill ? "rounded-full" : "rounded-[2px]",
        TONE_CLASSES[tone],
        className
      )}
    >
      {dot && <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", DOT_CLASSES[tone])} aria-hidden />}
      {icon}
      <span>{children}</span>
    </span>
  );
}

export function EvidenceStateBadge({
  state,
  className,
}: {
  state?: "CONFIRMED" | "SUSPECTED" | "INSUFFICIENT_EVIDENCE" | string | null;
  className?: string;
}) {
  if (state === "CONFIRMED") {
    return (
      <Badge tone="green" icon={<CheckCircle2 className="h-3 w-3" aria-hidden />} className={className}>
        Confirmed
      </Badge>
    );
  }
  if (state === "SUSPECTED") {
    return (
      <Badge tone="amber" icon={<HelpCircle className="h-3 w-3" aria-hidden />} className={className}>
        Suspected
      </Badge>
    );
  }
  if (state === "INSUFFICIENT_EVIDENCE") {
    return (
      <Badge tone="gray" icon={<CircleDashed className="h-3 w-3" aria-hidden />} className={className}>
        Initial Quiz Needed
      </Badge>
    );
  }
  return (
    <Badge tone="gray" icon={<TrendingUp className="h-3 w-3" aria-hidden />} className={className}>
      Estimated
    </Badge>
  );
}
