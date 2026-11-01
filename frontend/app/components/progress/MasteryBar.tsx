import { ArrowDownRight, ArrowRight, ArrowUpRight, Target } from "lucide-react";
import type { MasteryTrend } from "../../lib/types";
import { ProgressBar } from "../ui/Stat";

const TREND: Record<MasteryTrend, { label: string; className: string; icon: typeof ArrowRight | null }> = {
  improving: { label: "Improving", className: "text-accent-green", icon: ArrowUpRight },
  declining: { label: "Needs Review", className: "text-accent-red", icon: ArrowDownRight },
  stable: { label: "Stable", className: "text-muted", icon: ArrowRight },
  not_started: { label: "Not started", className: "text-muted", icon: null },
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
    <div className="flex flex-col gap-2 rounded-[2px] p-3.5 bg-surface border border-line hover:border-ink transition-colors">
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Target className="h-3.5 w-3.5 text-accent-red shrink-0" aria-hidden="true" />
          <span className="min-w-0 truncate font-serif text-[16px] text-ink">{topic}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          <span className={`inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.04em] ${t.className}`}>
            {Icon && <Icon className="h-3 w-3" aria-hidden="true" />}
            {t.label}
          </span>
          <span className="w-20 text-right font-mono text-xs tabular-nums text-ink">
            {pct}%
          </span>
        </div>
      </div>

      <ProgressBar value={score} label={`${topic} estimated mastery`} />

      <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.06em] text-muted">
        <span>
          {attempts === 0 ? "No quiz attempts yet" : `${attempts} quiz attempt${attempts === 1 ? "" : "s"}`}
        </span>
        <span>
          Estimated
        </span>
      </div>
    </div>
  );
}
