"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../lib/api";
import type {
  Category,
  Subject,
  TopicGraphResponse,
  TopicNode,
  UnclassifiedChunk,
} from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { TopicGraphEditor } from "../../components/subjects/TopicGraphEditor";

export default function SubjectsPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");

  const [newCategory, setNewCategory] = useState("");
  const [newSubjectName, setNewSubjectName] = useState("");
  const [newSubjectCategory, setNewSubjectCategory] = useState("");

  const [topics, setTopics] = useState<TopicNode[]>([]);
  const [drafting, setDrafting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [unclassified, setUnclassified] = useState<UnclassifiedChunk[]>([]);

  const loadCategories = useCallback(async () => {
    setCategories(await apiFetch<Category[]>("/categories"));
  }, []);

  const loadSubjects = useCallback(async () => {
    const rows = await apiFetch<Subject[]>("/subjects");
    setSubjects(rows);
    if (rows.length > 0 && !selectedSubjectId) setSelectedSubjectId(rows[0].id);
  }, [selectedSubjectId]);

  useEffect(() => {
    loadCategories();
    loadSubjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadGraph = useCallback(async (subjectId: string) => {
    if (!subjectId) return;
    const res = await apiFetch<TopicGraphResponse>(`/subjects/${subjectId}/topic-graph`);
    setTopics(res.topics);
    const uc = await apiFetch<UnclassifiedChunk[]>(`/subjects/${subjectId}/unclassified`);
    setUnclassified(uc);
  }, []);

  useEffect(() => {
    setMessage(null);
    setError(null);
    if (selectedSubjectId) loadGraph(selectedSubjectId);
  }, [selectedSubjectId, loadGraph]);

  async function handleCreateCategory(e: FormEvent) {
    e.preventDefault();
    if (!newCategory.trim()) return;
    await apiFetch("/categories", { method: "POST", body: { name: newCategory } });
    setNewCategory("");
    await loadCategories();
  }

  async function handleCreateSubject(e: FormEvent) {
    e.preventDefault();
    if (!newSubjectName.trim() || !newSubjectCategory) return;
    setError(null);
    try {
      const created = await apiFetch<Subject>("/subjects", {
        method: "POST",
        body: { name: newSubjectName, category_id: newSubjectCategory },
      });
      setNewSubjectName("");
      await loadSubjects();
      setSelectedSubjectId(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create subject.");
    }
  }

  async function handleDraft(file: File) {
    if (!selectedSubjectId) return;
    setDrafting(true);
    setError(null);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch<TopicGraphResponse>(`/subjects/${selectedSubjectId}/syllabus`, {
        method: "POST",
        body: form,
      });
      setTopics(res.topics);
      setMessage(`Drafted ${res.topics.length} topics — review and edit, then confirm.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Draft failed.");
    } finally {
      setDrafting(false);
    }
  }

  async function handleConfirm() {
    if (!selectedSubjectId) return;
    setConfirming(true);
    setError(null);
    setMessage(null);
    try {
      const res = await apiFetch<{ topic_count: number }>(
        `/subjects/${selectedSubjectId}/topic-graph`,
        { method: "PUT", body: { topics } }
      );
      setMessage(`Confirmed ${res.topic_count} topics.`);
      await loadGraph(selectedSubjectId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Confirm failed.");
    } finally {
      setConfirming(false);
    }
  }

  async function tagChunk(chunkId: string, topic: string) {
    await apiFetch(`/chunks/${chunkId}/topic`, { method: "PATCH", body: { topic } });
    setUnclassified((prev) => prev.filter((c) => c.chunk_id !== chunkId));
  }

  const categoryName = (id: string) => categories.find((c) => c.id === id)?.name ?? "—";

  return (
    <div className="max-w-4xl mx-auto flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-primary">Subjects &amp; Topic Graphs</h1>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Categories</h2>
        <div className="flex flex-wrap gap-2 mb-3">
          {categories.map((c) => (
            <span key={c.id} className="px-2 py-1 text-xs rounded bg-surface-muted text-secondary">
              {c.name}
            </span>
          ))}
          {categories.length === 0 && (
            <span className="text-sm text-tertiary">No categories yet.</span>
          )}
        </div>
        <form onSubmit={handleCreateCategory} className="flex gap-2">
          <Input
            placeholder="New category (e.g. Computer Science)"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" variant="secondary">
            Add category
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Create a subject</h2>
        <form onSubmit={handleCreateSubject} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Input
            label="Subject name"
            placeholder="e.g. Operating Systems"
            value={newSubjectName}
            onChange={(e) => setNewSubjectName(e.target.value)}
            className="flex-1"
          />
          <select
            className="px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary"
            value={newSubjectCategory}
            onChange={(e) => setNewSubjectCategory(e.target.value)}
          >
            <option value="">Choose category…</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <Button type="submit" disabled={!newSubjectName.trim() || !newSubjectCategory}>
            Create subject
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Topic Graph</h2>
        {subjects.length === 0 ? (
          <p className="text-sm text-tertiary">Create a subject above to build its topic graph.</p>
        ) : (
          <>
            <select
              className="w-full mb-4 px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary"
              value={selectedSubjectId}
              onChange={(e) => setSelectedSubjectId(e.target.value)}
            >
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {categoryName(s.category_id)} — {s.name}
                </option>
              ))}
            </select>

            <div className="flex items-center gap-3 mb-4">
              <label className="text-sm text-secondary">
                <span className="px-3 py-2 rounded-md bg-surface-muted border border-subtle cursor-pointer text-primary text-sm">
                  {drafting ? "Drafting…" : "Upload syllabus to draft"}
                </span>
                <input
                  type="file"
                  accept=".pdf,.pptx,.docx,.txt"
                  className="hidden"
                  disabled={drafting}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) handleDraft(f);
                    e.target.value = "";
                  }}
                />
              </label>
              <span className="text-xs text-tertiary">
                One AI call — the draft is not saved until you confirm.
              </span>
            </div>

            <TopicGraphEditor topics={topics} onChange={setTopics} />

            {error && <p className="text-sm text-danger mt-3">{error}</p>}
            {message && <p className="text-sm text-success mt-3">{message}</p>}

            <div className="mt-4">
              <Button onClick={handleConfirm} loading={confirming} disabled={topics.length === 0}>
                Confirm topic graph
              </Button>
            </div>
          </>
        )}
      </Card>

      {selectedSubjectId && unclassified.length > 0 && (
        <Card>
          <h2 className="font-semibold text-primary mb-1">Unclassified content</h2>
          <p className="text-sm text-tertiary mb-3">
            These chunks did not match a topic during ingestion. Tag them, or add a topic above and
            re-confirm.
          </p>
          <div className="flex flex-col gap-3">
            {unclassified.map((c) => (
              <div key={c.chunk_id} className="border border-subtle rounded-md p-3 text-sm">
                <div className="text-tertiary text-xs mb-1">
                  {c.document_title} · Unit {c.unit ?? "—"} / Ch {c.chapter ?? "—"}
                </div>
                <p className="text-secondary mb-2">{c.text_preview}…</p>
                <div className="flex flex-wrap gap-2">
                  {topics.map((t) => (
                    <button
                      key={t.topic}
                      onClick={() => tagChunk(c.chunk_id, t.topic)}
                      className="text-xs px-2 py-1 rounded border border-strong text-secondary hover:bg-app"
                      type="button"
                    >
                      {t.topic}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
