"use client";

import { useState } from "react";
import { Check, CheckCircle2, Clock, PlayCircle, X } from "lucide-react";
import { Card, CardHeader } from "../ui/Card";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Alert, EmptyState, SkeletonCard } from "../ui/Feedback";
import { useApi } from "../../lib/hooks/useApi";
import { apiFetch, errorMessage } from "../../lib/api";
import type { LearningResourceRow } from "../../lib/types";

interface EducatorModerationQueueProps {
  classId: string;
  onActionCompleted?: () => void;
}

export function EducatorModerationQueue({
  classId,
  onActionCompleted,
}: EducatorModerationQueueProps) {
  const pendingResources = useApi<LearningResourceRow[]>(
    `/resources?class_id=${classId}&status=pending_review`
  );
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function handleReview(resourceId: string, status: "approved" | "rejected") {
    setProcessingId(resourceId);
    setActionError(null);
    try {
      await apiFetch(`/resources/${resourceId}/review`, {
        method: "PATCH",
        body: { status },
      });
      pendingResources.reload();
      onActionCompleted?.();
    } catch (err) {
      setActionError(errorMessage(err, `Failed to ${status} resource.`));
    } finally {
      setProcessingId(null);
    }
  }

  const items = pendingResources.data ?? [];

  return (
    <Card>
      <CardHeader
        icon={<Clock className="h-5 w-5 text-accent-red" />}
        title="Student Video Suggestions"
        description="Review YouTube resources submitted by students. Approved videos will appear in class recommendations."
        actions={items.length > 0 ? <Badge tone="blue" pill>{items.length} pending</Badge> : undefined}
      />

      {actionError && <Alert tone="danger" className="mt-3">{actionError}</Alert>}

      {pendingResources.error ? (
        <Alert tone="danger" className="mt-4">
          {pendingResources.error}
        </Alert>
      ) : !pendingResources.data ? (
        <div className="mt-4 flex flex-col gap-3">
          <SkeletonCard lines={2} />
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<CheckCircle2 className="h-5 w-5 text-success" />}
          title="All suggestions reviewed"
          description="There are currently no pending student video suggestions waiting for approval."
          className="mt-4"
        />
      ) : (
        <div className="mt-4 flex flex-col divide-y divide-line">
          {items.map((item) => {
            const thumbUrl =
              item.thumbnail ||
              (item.video_id
                ? `https://i.ytimg.com/vi/${item.video_id}/hqdefault.jpg`
                : undefined);
            const isBusy = processingId === item.id;

            return (
              <div
                key={item.id}
                className="flex flex-col sm:flex-row items-start justify-between gap-4 py-4 first:pt-0 last:pb-0"
              >
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  {thumbUrl && (
                    <div className="relative aspect-video w-28 shrink-0 overflow-hidden rounded-[2px] bg-surface2">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={thumbUrl}
                        alt={item.title}
                        className="h-full w-full object-cover"
                      />
                      <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                        <PlayCircle className="h-6 w-6 text-white" />
                      </div>
                    </div>
                  )}

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 mb-1">
                      <Badge tone="blue">Student Suggestion</Badge>
                      <Badge tone="gray">{item.topic}</Badge>
                      <span className="font-mono text-[11px] text-muted">
                        by {item.uploaded_by_name || "Student"}
                      </span>
                    </div>

                    <a
                      href={item.url || "#"}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="font-serif text-[15px] text-ink hover:text-accent-red hover:underline line-clamp-2 transition-colors"
                    >
                      {item.title}
                    </a>
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-2 self-end sm:self-center">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={isBusy}
                    onClick={() => handleReview(item.id, "rejected")}
                    icon={<X className="h-3.5 w-3.5 text-danger" />}
                  >
                    Reject
                  </Button>
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={isBusy}
                    onClick={() => handleReview(item.id, "approved")}
                    icon={<Check className="h-3.5 w-3.5" />}
                  >
                    {isBusy ? "Reviewing…" : "Approve"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
