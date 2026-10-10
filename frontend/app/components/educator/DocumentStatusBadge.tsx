import { CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import type { DocumentStatus } from "../../lib/types";
import { Badge } from "../ui/Badge";

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  switch (status) {
    case "ready":
      return <Badge tone="green" icon={<CheckCircle2 className="h-3 w-3" aria-hidden />}>Ready</Badge>;
    case "failed":
      return <Badge tone="red" icon={<XCircle className="h-3 w-3" aria-hidden />}>Failed</Badge>;
    case "processing":
      return <Badge tone="info" icon={<Loader2 className="h-3 w-3 animate-spin" aria-hidden />}>Processing</Badge>;
    default:
      return <Badge tone="gray" icon={<Clock className="h-3 w-3" aria-hidden />}>Queued</Badge>;
  }
}
