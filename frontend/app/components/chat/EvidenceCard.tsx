import type { SourceType } from "../../lib/types";
import { Badge } from "../ui/Badge";

export function EvidenceCard({ sourceType, citationCount }: { sourceType: SourceType; citationCount: number }) {
  if (sourceType === "curriculum") {
    return (
      <div className="mt-2 flex items-center gap-2 text-xs">
        <Badge tone="green">From your curriculum</Badge>
        {citationCount > 0 && (
          <span className="text-gray-500">
            {citationCount} source{citationCount === 1 ? "" : "s"} referenced
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2 flex items-center gap-2 text-xs">
      <Badge tone="amber">General knowledge</Badge>
      <span className="text-gray-500">Not in your uploaded materials — verify independently</span>
    </div>
  );
}
