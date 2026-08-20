import type { MasteryTrend } from "../../lib/types";

const TREND_ARROW: Record<MasteryTrend, string> = {
  improving: "↑",
  declining: "↓",
  stable: "→",
  not_started: "",
};

const TREND_COLOR: Record<MasteryTrend, string> = {
  improving: "text-green-600",
  declining: "text-red-600",
  stable: "text-gray-400",
  not_started: "text-gray-300",
};

function barColor(score: number): string {
  if (score >= 0.7) return "bg-green-500";
  if (score >= 0.4) return "bg-amber-500";
  return "bg-red-500";
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
        <span className="text-gray-900">{topic}</span>
        <span className="flex items-center gap-1 text-gray-600">
          {pct}%
          <span className={TREND_COLOR[trend]}>{TREND_ARROW[trend]}</span>
          <span className="text-xs text-gray-400">({attempts} attempt{attempts === 1 ? "" : "s"})</span>
        </span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${barColor(score)}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
