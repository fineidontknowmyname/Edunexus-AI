"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, Info, Route } from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import { percent, plural } from "../../lib/format";
import type { ClassRow, LearningPathEntry, LearningPathResponse, RoutingMap } from "../../lib/types";
import type { BadgeTone } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Alert, EmptyState, ErrorState, SkeletonCard } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ProgressBar } from "../../components/ui/Stat";
import { StudentClassGate } from "../../components/layout/StudentClassGate";
import { RecommendationPanel } from "../../components/progress/RecommendationPanel";
import { cn } from "../../lib/cn";

const PRIORITY_LABEL: Record<number, { text: string; tone: BadgeTone }> = {
  0: { text: "Urgent: weak and attempted", tone: "red" },
  1: { text: "Urgent: not started, test soon", tone: "red" },
  2: { text: "Needs review", tone: "amber" },
  3: { text: "Not started", tone: "gray" },
  4: { text: "In progress", tone: "blue" },
  5: { text: "Strong", tone: "green" },
};

function ctaFor(entry: LearningPathEntry) {
  return entry.attempts === 0 ? { href: "/quiz", label: "Take a quiz" } : { href: "/chat", label: "Ask the tutor" };
}

export default function LearningPathPage() {
  return <StudentClassGate width="narrow">{(activeClass, picker) => <LearningPath key={activeClass.id} activeClass={activeClass} picker={picker} />}</StudentClassGate>;
}

function LearningPath({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const path = useApi<LearningPathResponse>(`/progress/path?class_id=${activeClass.id}`);
  const routing = useApi<RoutingMap>(`/progress/routing?class_id=${activeClass.id}`);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggle(topic: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) next.delete(topic);
      else next.add(topic);
      return next;
    });
  }

  return (
    <PageContainer width="narrow">
      <PageHeader
        title="Learning path"
        description="Your topics in the order that will help most, based on mastery, the syllabus and upcoming assessments."
        actions={picker()}
      />

      {path.error ? (
        <ErrorState message={path.error} onRetry={path.reload} />
      ) : !path.data ? (
        <div className="flex flex-col gap-3" role="status">
          <span className="sr-only">Loading learning path…</span>
          {[0, 1, 2, 3].map((i) => (
            <SkeletonCard key={i} lines={1} />
          ))}
        </div>
      ) : (
        <>
          {path.data.cold_start && (
            <Alert tone="info" title="This is syllabus order for now">
              Complete a quiz and your path will reorder around what you need most.
            </Alert>
          )}

          {path.data.path.length === 0 ? (
            <EmptyState
              icon={<Route className="h-5 w-5" />}
              title="No topics tracked yet"
              description="Ask your teacher to upload course notes, or take a quiz to get started."
              action={
                <Link href="/quiz" className="text-sm font-medium text-accent-secondary hover:underline">
                  Browse quizzes
                </Link>
              }
            />
          ) : (
            <ol className="flex flex-col gap-3">
              {path.data.path.map((entry, index) => {
                const label = PRIORITY_LABEL[entry.priority] ?? PRIORITY_LABEL[3];
                const cta = ctaFor(entry);
                const isOpen = expanded.has(entry.topic);
                const panelId = `help-${index}`;
                const needsGuidance = routing.data?.[entry.topic] === "intervene";
                return (
                  <Card as="li" key={entry.topic} className="p-4 sm:p-5">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                      <span
                        className={cn(
                          "hidden h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold sm:flex",
                          index === 0 ? "bg-accent-secondary text-on-accent" : "bg-surface-muted text-secondary"
                        )}
                        aria-hidden
                      >
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <h2 className="mr-1 text-[0.9375rem] font-semibold text-primary">{entry.topic}</h2>
                          <Badge tone={label.tone} dot>{label.text}</Badge>
                          {entry.in_assessment_scope && <Badge tone="red">In exam scope</Badge>}
                          {needsGuidance && <Badge tone="amber">Guided session suggested</Badge>}
                        </div>
                        <div className="mt-2 flex items-center gap-3">
                          <ProgressBar value={entry.mastery_score} label={`${entry.topic} mastery`} className="max-w-[12rem]" />
                          <span className="shrink-0 text-xs text-tertiary">
                            {entry.attempts === 0 ? "Not attempted yet" : `${percent(entry.mastery_score)} · ${plural(entry.attempts, "attempt")}`}
                          </span>
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <button
                          type="button"
                          onClick={() => toggle(entry.topic)}
                          aria-expanded={isOpen}
                          aria-controls={panelId}
                          className="inline-flex h-8 items-center gap-1 rounded-lg border border-strong bg-surface px-3 text-xs font-medium text-primary hover:bg-surface-muted"
                        >
                          {isOpen ? "Hide help" : "Get help"}
                          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", isOpen && "rotate-180")} aria-hidden />
                        </button>
                        <Link
                          href={cta.href}
                          className="inline-flex h-8 items-center rounded-lg px-3 text-xs font-medium text-accent-secondary hover:bg-accent-secondary/10"
                        >
                          {cta.label}
                        </Link>
                      </div>
                    </div>
                    {isOpen && (
                      <div id={panelId}>
                        <RecommendationPanel classId={activeClass.id} topic={entry.topic} />
                      </div>
                    )}
                  </Card>
                );
              })}
            </ol>
          )}
          <p className="flex items-center gap-1.5 text-xs text-tertiary">
            <Info className="h-3.5 w-3.5" aria-hidden />
            Path for {activeClass.name}
          </p>
        </>
      )}
    </PageContainer>
  );
}
