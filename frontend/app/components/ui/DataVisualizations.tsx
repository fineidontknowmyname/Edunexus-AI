import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function ProgressRing({
  value,
  size = 116,
  strokeWidth = 9,
  label,
  sublabel,
  className,
  color = "stroke-red",
}: {
  value: number; // 0 to 1 or 0 to 100
  size?: number;
  strokeWidth?: number;
  label?: ReactNode;
  sublabel?: string;
  className?: string;
  color?: string;
}) {
  const normalized = value > 1 ? value : Math.round(value * 100);
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (Math.min(100, Math.max(0, normalized)) / 100) * circumference;

  return (
    <div
      role="progressbar"
      aria-label={typeof label === "string" ? label : "Progress metric"}
      aria-valuenow={normalized}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("relative inline-flex items-center justify-center select-none", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="rotate-[-90deg]">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          className="stroke-surface2"
          strokeWidth={strokeWidth}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          className={cn("transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]", color)}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="butt"
          fill="none"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="font-serif text-3xl font-normal tabular-nums text-ink leading-none">
          {label ?? `${normalized}%`}
        </span>
        {sublabel && (
          <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.08em] text-muted leading-tight">
            {sublabel}
          </span>
        )}
      </div>
    </div>
  );
}

export interface DonutSegment {
  label: string;
  count: number;
  colorClass: string;
  badgeTone?: "green" | "amber" | "red" | "blue" | "gray";
}

export function DonutChart({
  segments,
  size = 140,
  strokeWidth = 12,
  centerTitle,
  centerSubtitle,
}: {
  segments: DonutSegment[];
  size?: number;
  strokeWidth?: number;
  centerTitle?: string;
  centerSubtitle?: string;
}) {
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  const radius = (size - strokeWidth * 2) / 2;
  const circumference = 2 * Math.PI * radius;

  let accumulated = 0;

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="rotate-[-90deg]">
          {total === 0 ? (
            <circle
              cx={size / 2}
              cy={size / 2}
              r={radius}
              className="stroke-surface2"
              strokeWidth={strokeWidth}
              fill="none"
            />
          ) : (
            segments.map((seg, i) => {
              if (seg.count <= 0) return null;
              const segPct = seg.count / total;
              const strokeDash = segPct * circumference;
              const strokeOffset = circumference - accumulated * circumference;
              accumulated += segPct;

              return (
                <circle
                  key={i}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  className={cn("transition-all duration-500", seg.colorClass)}
                  strokeWidth={strokeWidth}
                  strokeDasharray={`${strokeDash} ${circumference - strokeDash}`}
                  strokeDashoffset={strokeOffset}
                  fill="none"
                />
              );
            })
          )}
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="font-serif text-3xl tabular-nums text-ink leading-tight font-normal">
            {centerTitle ?? total}
          </span>
          <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-muted">
            {centerSubtitle ?? "Total"}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 font-mono text-[9px] uppercase tracking-[0.08em]">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <span className={cn("h-2 w-2 rounded-full shrink-0", seg.colorClass.replace("stroke-", "bg-"))} aria-hidden />
            <span className="text-muted">{seg.label}:</span>
            <span className="font-bold text-ink tabular-nums">{seg.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MiniBarList({
  items,
}: {
  items: { label: string; value: number; sublabel?: string; highlight?: boolean }[];
}) {
  return (
    <div className="space-y-4">
      {items.map((it, idx) => {
        const pct = Math.max(0, Math.min(100, Math.round(it.value * 100)));
        return (
          <div key={idx} className="space-y-1">
            <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.08em]">
              <span className={cn("truncate max-w-[70%]", it.highlight ? "text-red" : "text-muted")}>
                {it.label}
              </span>
              <span className="tabular-nums text-ink">
                {pct}%
              </span>
            </div>
            <div className="progress-line">
              <span className={it.highlight ? "bg-red" : "bg-red/70"} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
