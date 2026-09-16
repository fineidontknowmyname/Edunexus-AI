"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";
import type { ClassRow, LearningPathEntry, LearningPathResponse } from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { RecommendationPanel } from "../../components/progress/RecommendationPanel";

const PRIORITY_LABEL: Record<number, { text: string; tone: "red" | "amber" | "gray" | "blue" | "green" }> = {
  0: { text: "Urgent — weak & attempted", tone: "red" },
  1: { text: "Urgent — not started, test soon", tone: "red" },
  2: { text: "Needs review", tone: "amber" },
  3: { text: "Not started", tone: "gray" },
  4: { text: "In progress", tone: "blue" },
  5: { text: "Strong", tone: "green" },
};

function ctaFor(entry: LearningPathEntry) {
  return entry.attempts === 0
    ? { href: "/quiz", label: "Take a quiz" }
    : { href: "/chat", label: "Ask about this" };
}

export default function LearningPathPage() {
  const [data, setData] = useState<LearningPathResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [classes, setClasses] = useState<ClassRow[] | null>(null);
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set());

  useEffect(() => {
    apiFetch<LearningPathResponse>("/progress/path")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load learning path."));
  }, []);

  useEffect(() => {
    apiFetch<ClassRow[]>("/classes/").then(setClasses);
  }, []);

  function toggleExpanded(topic: string) {
    setExpandedTopics((prev) => {
      const next = new Set(prev);
      if (next.has(topic)) {
        next.delete(topic);
      } else {
        next.add(topic);
      }
      return next;
    });
  }

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!data) return <p className="text-sm text-tertiary">Loading…</p>;

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-primary">Learning Path</h1>

      {data.cold_start && (
        <p className="text-sm text-tertiary">
          This is syllabus order — complete a quiz to personalize your path.
        </p>
      )}

      {data.path.length === 0 && (
        <p className="text-sm text-tertiary">
          No topics tracked yet — ask your teacher to upload notes, or take a quiz to get started.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {data.path.map((entry) => {
          const label = PRIORITY_LABEL[entry.priority];
          const cta = ctaFor(entry);
          const expanded = expandedTopics.has(entry.topic);
          return (
            <Card key={entry.topic}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-primary">{entry.topic}</span>
                    <Badge tone={label.tone}>{label.text}</Badge>
                    {entry.in_assessment_scope && <Badge tone="red">In exam scope</Badge>}
                  </div>
                  <p className="text-xs text-tertiary mt-1">
                    {entry.attempts === 0
                      ? "Not attempted yet"
                      : `${Math.round(entry.mastery_score * 100)}% mastery · ${entry.attempts} attempt${entry.attempts === 1 ? "" : "s"}`}
                  </p>
                </div>
                <div className="flex items-center gap-4 ml-4">
                  <button
                    onClick={() => toggleExpanded(entry.topic)}
                    className="text-sm text-accent-secondary hover:underline whitespace-nowrap"
                  >
                    {expanded ? "Hide help" : "Get help"}
                  </button>
                  <Link href={cta.href} className="text-sm text-accent-secondary hover:underline whitespace-nowrap">
                    {cta.label}
                  </Link>
                </div>
              </div>
              {expanded && classes?.[0]?.id && (
                <RecommendationPanel classId={classes[0].id} topic={entry.topic} />
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
