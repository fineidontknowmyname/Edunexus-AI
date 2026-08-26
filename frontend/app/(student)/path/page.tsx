"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "../../lib/api";
import type { LearningPathEntry, LearningPathResponse } from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";

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

  useEffect(() => {
    apiFetch<LearningPathResponse>("/progress/path")
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load learning path."));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!data) return <p className="text-sm text-gray-500">Loading…</p>;

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-gray-900">Learning Path</h1>

      {data.cold_start && (
        <p className="text-sm text-gray-500">
          This is syllabus order — complete a quiz to personalize your path.
        </p>
      )}

      {data.path.length === 0 && (
        <p className="text-sm text-gray-500">
          No topics tracked yet — ask your teacher to upload notes, or take a quiz to get started.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {data.path.map((entry) => {
          const label = PRIORITY_LABEL[entry.priority];
          const cta = ctaFor(entry);
          return (
            <Card key={entry.topic} className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">{entry.topic}</span>
                  <Badge tone={label.tone}>{label.text}</Badge>
                  {entry.in_assessment_scope && <Badge tone="red">In exam scope</Badge>}
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  {entry.attempts === 0
                    ? "Not attempted yet"
                    : `${Math.round(entry.mastery_score * 100)}% mastery · ${entry.attempts} attempt${entry.attempts === 1 ? "" : "s"}`}
                </p>
              </div>
              <Link href={cta.href} className="text-sm text-blue-600 hover:underline whitespace-nowrap ml-4">
                {cta.label}
              </Link>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
