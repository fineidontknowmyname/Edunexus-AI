"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../../lib/api";
import type { ClassContextResponse, DocumentRow } from "../../lib/types";
import { Card } from "../ui/Card";

interface ChapterEntry {
  chapter: number;
  chapterName: string;
  taught: boolean;
}

export function SyllabusChecklist({ classId, documents }: { classId: string; documents: DocumentRow[] }) {
  const [syllabus, setSyllabus] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

  useEffect(() => {
    if (!classId) return;
    setLoading(true);
    apiFetch<ClassContextResponse>(`/context/class/${classId}`)
      .then((ctx) => setSyllabus(ctx.syllabus))
      .finally(() => setLoading(false));
  }, [classId]);

  const chapterMap = new Map<number, string>();
  for (const doc of documents) {
    if (doc.chapter != null) {
      chapterMap.set(doc.chapter, doc.chapter_name || `Chapter ${doc.chapter}`);
    }
  }
  const chapters: ChapterEntry[] = Array.from(chapterMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([chapter, chapterName]) => ({
      chapter,
      chapterName,
      taught: syllabus[String(chapter)] === "taught",
    }));

  // Topic-keyed entries are auto-marked at ingestion from chunk classification.
  const topicsCovered = Object.entries(syllabus)
    .filter(([key, status]) => status === "taught" && !/^\d+$/.test(key))
    .map(([topic]) => topic)
    .sort();

  async function toggle(chapter: number, currentlyTaught: boolean) {
    setSaving(chapter);
    const nextStatus = currentlyTaught ? "not_taught" : "taught";
    try {
      await apiFetch(`/context/class/${classId}/syllabus`, {
        method: "PATCH",
        body: { chapter, status: nextStatus },
      });
      setSyllabus((prev) => ({ ...prev, [String(chapter)]: nextStatus }));
    } finally {
      setSaving(null);
    }
  }

  if (loading) return null;

  return (
    <Card>
      <h2 className="font-semibold text-primary mb-3">Syllabus progress</h2>
      {chapters.length === 0 ? (
        <p className="text-sm text-tertiary">Upload a document with a chapter number to track progress here.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {chapters.map((c) => (
            <label
              key={c.chapter}
              className="flex items-center gap-3 px-3 py-2 rounded-md border border-subtle text-sm cursor-pointer hover:bg-app"
            >
              <input
                type="checkbox"
                checked={c.taught}
                disabled={saving === c.chapter}
                onChange={() => toggle(c.chapter, c.taught)}
              />
              <span className={c.taught ? "text-primary" : "text-tertiary"}>
                Chapter {c.chapter} — {c.chapterName}
              </span>
              {c.taught && <span className="ml-auto text-xs text-success">Taught</span>}
            </label>
          ))}
        </div>
      )}

      {topicsCovered.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-secondary mb-2">Topics covered (auto-detected)</h3>
          <div className="flex flex-wrap gap-2">
            {topicsCovered.map((t) => (
              <span
                key={t}
                className="px-2 py-1 text-xs rounded bg-surface-muted text-secondary border border-subtle"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
