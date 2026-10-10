import { BookOpenCheck, Globe } from "lucide-react";
import type { SourceType } from "../../lib/types";
import { Badge } from "../ui/Badge";

export function EvidenceCard({ sourceType, citationCount }: { sourceType: SourceType; citationCount: number }) {
  if (sourceType === "curriculum") {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="green" icon={<BookOpenCheck className="h-3 w-3" aria-hidden />}>
          From your curriculum
        </Badge>
        {citationCount > 0 && (
          <span className="text-tertiary">
            Grounded in {citationCount} passage{citationCount === 1 ? "" : "s"} from your course materials
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge tone="amber" icon={<Globe className="h-3 w-3" aria-hidden />}>
        General knowledge
      </Badge>
      <span className="text-tertiary">Not found in your course materials, so double-check it</span>
    </div>
  );
}
