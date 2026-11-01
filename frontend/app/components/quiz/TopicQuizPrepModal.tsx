"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  BookOpen,
  Clock,
  ListChecks,
  Loader2,
  PlayCircle,
  RotateCcw,
  Target,
} from "lucide-react";
import { Modal } from "../ui/Modal";
import { Button, ButtonLink } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Alert } from "../ui/Feedback";
import { percent, plural } from "../../lib/format";
import { apiFetch, ApiError } from "../../lib/api";
import type { TopicQuizPrepContext, TopicQuizResponse } from "../../lib/types";

interface TopicQuizPrepModalProps {
  open: boolean;
  onClose: () => void;
  context: TopicQuizPrepContext | null;
  onLearnConcept?: () => void;
}

export function TopicQuizPrepModal({
  open,
  onClose,
  context,
  onLearnConcept,
}: TopicQuizPrepModalProps) {
  const router = useRouter();
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!context) return null;

  const scorePct = context.mastery_score != null ? percent(context.mastery_score) : null;
  const isLow = context.mastery_score != null && context.mastery_score < 0.6;
  const attempts = context.attempts ?? 0;

  const handleStartAssessment = async () => {
    if (!context.class_id || !context.topic || isGenerating) return;
    setIsGenerating(true);
    setError(null);

    try {
      const res = await apiFetch<TopicQuizResponse>("/quizzes/topic-quiz", {
        method: "POST",
        body: JSON.stringify({
          class_id: context.class_id,
          topic: context.topic,
          topic_id: context.topic_id || undefined,
          num_questions: 5,
        }),
      });

      onClose();
      router.push(
        `/quiz/${res.quiz_id}?topic=${encodeURIComponent(context.topic)}&origin=recommendations`
      );
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || "Failed to generate topic assessment.");
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred while preparing your assessment.");
      }
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        if (!isGenerating) {
          setError(null);
          onClose();
        }
      }}
      bracket="ASSESSMENT PREP"
      title="Topic Assessment Preparation"
      description="Calibrate your understanding with a targeted topic evaluation."
    >
      <div className="flex flex-col gap-4 text-xs">
        {/* Topic Banner */}
        <div className="rounded-[2px] border border-line bg-surface2/60 p-4">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {context.subject_name && (
              <Badge tone="gray">{context.subject_name}</Badge>
            )}
            {context.class_name && (
              <span className="font-mono text-[9px] uppercase tracking-wider text-muted">
                {context.class_name}
              </span>
            )}
            {scorePct ? (
              <Badge tone={isLow ? "red" : "amber"} dot>
                Est. {scorePct}
              </Badge>
            ) : (
              <Badge tone="gray">Diagnostic</Badge>
            )}
          </div>

          <h3 className="font-serif text-2xl text-ink flex items-center gap-2 leading-tight">
            <Target className="h-4 w-4 text-red shrink-0" aria-hidden="true" />
            <span>{context.topic}</span>
          </h3>

          <p className="mt-1.5 font-sans text-xs text-muted leading-relaxed">
            {attempts > 0
              ? `You have completed ${attempts} ${plural(attempts, "attempt")} on this topic. This assessment will re-evaluate your understanding.`
              : "No previous attempts logged. This assessment will establish your baseline mastery estimate."}
          </p>
        </div>

        {/* Specs */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="rounded-[2px] border border-line bg-surface p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase text-muted">
              <ListChecks className="h-3 w-3 text-red" />
              <span>Format</span>
            </div>
            <p className="mt-1 font-serif text-lg text-ink">5 Diagnostic Items</p>
            <p className="font-mono text-[9px] text-muted">SC, MC &amp; True/False</p>
          </div>

          <div className="rounded-[2px] border border-line bg-surface p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase text-muted">
              <Clock className="h-3 w-3 text-red" />
              <span>Pacing</span>
            </div>
            <p className="mt-1 font-serif text-lg text-ink">~8 Minutes</p>
            <p className="font-mono text-[9px] text-muted">Untimed practice mode</p>
          </div>
        </div>

        {/* Status / Loading / Error */}
        {isGenerating ? (
          <div className="rounded-[2px] border border-line bg-surface2 p-4 flex items-center gap-3">
            <Loader2 className="h-4 w-4 animate-spin text-red shrink-0" />
            <div>
              <p className="font-mono text-xs uppercase tracking-wider text-ink font-semibold">Generating Assessment…</p>
              <p className="font-sans text-xs text-muted mt-0.5">
                Grounding questions in class curriculum for <b>{context.topic}</b>.
              </p>
            </div>
          </div>
        ) : error ? (
          <Alert tone="danger">
            <div className="flex flex-col gap-2 font-mono text-xs">
              <p>{error}</p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleStartAssessment}
                  icon={<RotateCcw className="h-3 w-3" />}
                >
                  Try Again
                </Button>
                {onLearnConcept && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setError(null);
                      onClose();
                      onLearnConcept();
                    }}
                  >
                    Learn Concept First ↗
                  </Button>
                )}
              </div>
            </div>
          </Alert>
        ) : (
          <div className="rounded-[2px] border border-line bg-surface2/40 p-3 font-mono text-[9px] uppercase tracking-wider text-muted">
            Questions are dynamically grounded in approved curriculum documents for <b>{context.topic}</b>.
          </div>
        )}

        {/* Action Controls */}
        <div className="mt-2 flex flex-col gap-2 pt-3 border-t border-line">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {onLearnConcept ? (
              <Button
                variant="outline"
                size="sm"
                icon={<BookOpen className="h-3.5 w-3.5" />}
                disabled={isGenerating}
                onClick={() => {
                  setError(null);
                  onClose();
                  onLearnConcept();
                }}
              >
                Learn Concept ↗
              </Button>
            ) : (
              <ButtonLink
                href="/path"
                variant="outline"
                size="sm"
                icon={<BookOpen className="h-3.5 w-3.5" />}
              >
                Curriculum Path ↗
              </ButtonLink>
            )}

            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setError(null);
                  onClose();
                }}
                disabled={isGenerating}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={
                  isGenerating ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <PlayCircle className="h-3.5 w-3.5" />
                  )
                }
                disabled={isGenerating || !context.class_id}
                onClick={handleStartAssessment}
              >
                {isGenerating ? "Preparing…" : "Start Assessment →"}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
