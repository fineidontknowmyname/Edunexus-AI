import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import type { MasteryTrend } from "../../lib/types";
import { ProgressBar } from "../ui/Stat";

const TREND: Record<MasteryTrend, { label: string; className: string; icon: typeof ArrowRight | null }> = {
  improving: { label: "Improving", className: "text-success", icon: ArrowUpRight },
  declining: { label: "Declining", className: "text-danger", icon: ArrowDownRight },
  stable: { label: "Stable", className: "text-tertiary", icon: ArrowRight },
  not_started: { label: "Not started", className: "text-tertiary", icon: null },
};

export function MasteryBar({
  topic,
  score,
  trend,
  attempts,
}: {
  topic: string;
  score: number;
  trend: MasteryTrend;
  attempts: number;
}) {
  const pct = Math.round(score * 100);
  const t = TREND[trend] ?? TREND.stable;
  const Icon = t.icon;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="min-w-0 truncate font-medium text-primary">{topic}</span>
        <span className="flex shrink-0 items-center gap-2">
          <span className={`inline-flex items-center gap-0.5 text-xs ${t.className}`}>
            {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
            {t.label}
          </span>
          <span className="w-10 text-right font-semibold tabular-nums text-primary">{pct}%</span>
        </span>
      </div>
      <ProgressBar value={score} label={`${topic} mastery`} />
      <span className="text-xs text-tertiary">
        {attempts} attempt{attempts === 1 ? "" : "s"}
      </span>
    </div>
  );
}
