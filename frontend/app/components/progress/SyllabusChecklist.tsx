"use client";

import { useState } from "react";
import { BookMarked, Check } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import type { ClassContextResponse, DocumentRow } from "../../lib/types";
import { Card, CardHeader } from "../ui/Card";
import { Alert, ErrorState, SkeletonText } from "../ui/Feedback";
import { ProgressBar } from "../ui/Stat";
import { cn } from "../../lib/cn";

export function SyllabusChecklist({ classId, documents }: { classId: string; documents: DocumentRow[] }) {
  const context = useApi<ClassContextResponse>(`/context/class/${classId}`);
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const syllabus = context.data?.syllabus ?? {};

  const chapterMap = new Map<number, string>();
  for (const doc of documents) {
    if (doc.chapter != null && !chapterMap.has(doc.chapter)) {
      chapterMap.set(doc.chapter, doc.chapter_name || `Chapter ${doc.chapter}`);
    }
  }
  const chapters = Array.from(chapterMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([chapter, chapterName]) => ({ chapter, chapterName, taught: syllabus[String(chapter)] === "taught" }));
  const taughtCount = chapters.filter((c) => c.taught).length;

  const topicsCovered = Object.entries(syllabus)
    .filter(([key, status]) => status === "taught" && !/^\d+$/.test(key))
    .map(([topic]) => topic)
    .sort();

  async function toggle(chapter: number, currentlyTaught: boolean) {
    setSaving(chapter);
    setError(null);
    const nextStatus = currentlyTaught ? "not_taught" : "taught";
    try {
      await apiFetch(`/context/class/${classId}/syllabus`, { method: "PATCH", body: { chapter, status: nextStatus } });
      context.mutate((prev) => (prev ? { ...prev, syllabus: { ...prev.syllabus, [String(chapter)]: nextStatus } } : prev));
    } catch (err) {
      setError(errorMessage(err, "Couldn't update the syllabus."));
    } finally {
      setSaving(null);
    }
  }

  return (
    <Card>
      <CardHeader
        icon={<BookMarked className="h-4 w-4" />}
        title="Syllabus progress"
        description="Mark chapters as taught. The tutor and learning paths prioritise taught material."
      />
      {context.error ? (
        <ErrorState message={context.error} onRetry={context.reload} />
      ) : !context.data ? (
        <SkeletonText lines={3} />
      ) : chapters.length === 0 ? (
        <p className="text-sm text-tertiary">Upload a document with a chapter number to track it here.</p>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-3">
            <ProgressBar value={chapters.length ? taughtCount / chapters.length : 0} label="Chapters taught" />
            <span className="shrink-0 font-mono text-xs tabular-nums text-muted">
              {taughtCount}/{chapters.length}
            </span>
          </div>
          <ul className="flex flex-col gap-1.5">
            {chapters.map((c) => (
              <li key={c.chapter}>
                <label
                  className={cn(
                    "flex items-center gap-3 rounded-[2px] border px-3 py-2 text-sm transition-colors",
                    c.taught ? "border-accent-green/40 bg-accent-green/5" : "border-line bg-surface hover:bg-surface2",
                    saving === c.chapter ? "opacity-60" : "cursor-pointer"
                  )}
                >
                  <input
                    type="checkbox"
                    checked={c.taught}
                    disabled={saving !== null}
                    onChange={() => toggle(c.chapter, c.taught)}
                    className="sr-only"
                  />
                  <span
                    className={cn(
                      "flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] border transition-colors",
                      c.taught ? "border-accent-green bg-accent-green text-white" : "border-line bg-surface"
                    )}
                    aria-hidden
                  >
                    {c.taught && <Check className="h-3 w-3" strokeWidth={3} />}
                  </span>
                  <span className={cn("min-w-0 truncate font-serif text-[15px]", c.taught ? "text-ink" : "text-muted")}>
                    <span className="font-mono text-xs uppercase tracking-[0.04em] text-muted">Ch {String(c.chapter).padStart(2, "0")} · </span>
                    {c.chapterName}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </>
      )}
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}

      {topicsCovered.length > 0 && (
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Topics covered (auto-detected)</h3>
          <div className="flex flex-wrap gap-1.5">
            {topicsCovered.map((t) => (
              <span key={t} className="rounded-full border border-line bg-surface2 px-2.5 py-0.5 font-mono text-[11px] text-ink uppercase tracking-[0.04em]">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
