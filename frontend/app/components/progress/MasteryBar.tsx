import type { MasteryTrend } from "../../lib/types";

const TREND_ARROW: Record<MasteryTrend, string> = {
  improving: "↑",
  declining: "↓",
  stable: "→",
  not_started: "",
};

const TREND_COLOR: Record<MasteryTrend, string> = {
  improving: "text-success",
  declining: "text-danger",
  stable: "text-tertiary",
  not_started: "text-tertiary",
};

function barColor(score: number): string {
  if (score >= 0.7) return "bg-success";
  if (score >= 0.4) return "bg-warning";
  return "bg-danger";
}

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
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-sm">
        <span className="text-primary">{topic}</span>
        <span className="flex items-center gap-1 text-secondary">
          {pct}%
          <span className={TREND_COLOR[trend]}>{TREND_ARROW[trend]}</span>
          <span className="text-xs text-tertiary">({attempts} attempt{attempts === 1 ? "" : "s"})</span>
        </span>
      </div>
      <div className="w-full h-2 bg-surface-muted rounded-full overflow-hidden">
        <div className={`h-full ${barColor(score)}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
