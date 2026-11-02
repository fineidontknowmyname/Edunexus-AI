import { getRecommendationPresentation, type RecommendationMode } from "../../lib/recommendationPresentation";
import { Badge } from "../ui/Badge";

export function RecommendationModeBanner({
  mode,
  reason,
}: {
  mode: RecommendationMode;
  reason?: string | null;
}) {
  const presentation = getRecommendationPresentation(mode, reason);
  return (
    <div className="rounded-[2px] border border-line bg-surface2 p-4">
      <div className="mb-1">
        <Badge tone={mode === "initial_assessment" ? "amber" : "gray"}>
          {presentation.label}
        </Badge>
      </div>
      <h4 className="font-serif text-[16px] text-ink">{presentation.title}</h4>
      <p className="mt-1 text-xs text-muted">{presentation.description}</p>
    </div>
  );
}
