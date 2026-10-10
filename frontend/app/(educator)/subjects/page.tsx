"use client";

import { FormEvent, useRef, useState } from "react";
import { BookOpen, FileSearch, FolderTree, GitBranch, Plus, ShieldAlert, Sparkles, Tag } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi, useAsync } from "../../lib/hooks/useApi";
import type {
  Category,
  MisconceptionRule,
  Subject,
  TopicGraphResponse,
  TopicNode,
  UnclassifiedChunk,
} from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Input, Select } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonText } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { TopicGraphEditor } from "../../components/subjects/TopicGraphEditor";
import { MisconceptionRulesEditor } from "../../components/subjects/MisconceptionRulesEditor";
import { plural } from "../../lib/format";

type Message = { tone: "success" | "danger"; text: string } | null;

export default function SubjectsPage() {
  const categories = useApi<Category[]>("/categories");
  const subjects = useApi<Subject[]>("/subjects");
  const [chosenId, setChosenId] = useState<string | null>(null);

  if (categories.error || subjects.error) {
    return (
      <PageContainer>
        <PageHeader title="Subjects & topics" />
        <ErrorState
          message={categories.error ?? subjects.error}
          onRetry={() => {
            categories.reload();
            subjects.reload();
          }}
        />
      </PageContainer>
    );
  }
  if (!categories.data || !subjects.data) {
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  }

  const subjectList = subjects.data;
  const selectedId = subjectList.some((s) => s.id === chosenId) ? (chosenId as string) : subjectList[0]?.id ?? "";
  const categoryName = (id: string) => categories.data?.find((c) => c.id === id)?.name ?? "Uncategorised";

  return (
    <PageContainer>
      <PageHeader
        title="Subjects & topics"
        description="Define each subject's topic graph. It drives topic tagging, learning paths and misconception detection."
        actions={
          subjectList.length > 0 ? (
            <Select label="Subject" srOnlyLabel value={selectedId} onChange={(e) => setChosenId(e.target.value)} wrapperClassName="w-full sm:w-72">
              {subjectList.map((s) => (
                <option key={s.id} value={s.id}>
                  {categoryName(s.category_id)} · {s.name}
                </option>
              ))}
            </Select>
          ) : undefined
        }
      />

      <div className="grid gap-6 md:grid-cols-2">
        <CategoriesCard categories={categories.data} onCreated={categories.reload} />
        <CreateSubjectCard
          categories={categories.data}
          onCreated={(s) => {
            subjects.reload();
            setChosenId(s.id);
          }}
        />
      </div>

      {subjectList.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="h-5 w-5" />}
          title="No subjects yet"
          description="Create a category and a subject above, then upload a syllabus to draft its topic graph."
        />
      ) : (
        <SubjectWorkspace key={selectedId} subject={subjectList.find((s) => s.id === selectedId) as Subject} />
      )}
    </PageContainer>
  );
}

function CategoriesCard({ categories, onCreated }: { categories: Category[]; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch("/categories", { method: "POST", body: { name: name.trim() } });
      setName("");
      onCreated();
    } catch (err) {
      setError(errorMessage(err, "Couldn't create the category."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader icon={<FolderTree className="h-4 w-4" />} title="Categories" description="Group related subjects." />
      <div className="mb-4 flex flex-wrap gap-1.5">
        {categories.length === 0 ? (
          <span className="text-sm text-tertiary">No categories yet.</span>
        ) : (
          categories.map((c) => <Badge key={c.id}>{c.name}</Badge>)
        )}
      </div>
      <form onSubmit={handleCreate} className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <Input label="New category" srOnlyLabel placeholder="e.g. Computer Science" value={name} onChange={(e) => setName(e.target.value)} wrapperClassName="flex-1" />
        <Button type="submit" variant="secondary" loading={saving} disabled={!name.trim()} icon={<Plus className="h-4 w-4" aria-hidden />}>
          Add
        </Button>
      </form>
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
    </Card>
  );
}

function CreateSubjectCard({ categories, onCreated }: { categories: Category[]; onCreated: (s: Subject) => void }) {
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const effectiveCategory = categoryId || categories[0]?.id || "";

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !effectiveCategory) return;
    setSaving(true);
    setError(null);
    try {
      const created = await apiFetch<Subject>("/subjects", { method: "POST", body: { name: name.trim(), category_id: effectiveCategory } });
      setName("");
      onCreated(created);
    } catch (err) {
      setError(errorMessage(err, "Couldn't create the subject."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader icon={<BookOpen className="h-4 w-4" />} title="New subject" description="Each subject has its own topic graph." />
      <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
        <Input label="Subject name" placeholder="e.g. Operating Systems" value={name} onChange={(e) => setName(e.target.value)} />
        <Select label="Category" value={effectiveCategory} onChange={(e) => setCategoryId(e.target.value)} disabled={categories.length === 0}>
          {categories.length === 0 && <option value="">Create a category first</option>}
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </Select>
        <div className="sm:col-span-2">
          <Button type="submit" loading={saving} disabled={!name.trim() || !effectiveCategory}>
            Create subject
          </Button>
        </div>
      </form>
      {error && <Alert tone="danger" className="mt-3">{error}</Alert>}
    </Card>
  );
}

interface SubjectData {
  topics: TopicNode[];
  unclassified: UnclassifiedChunk[];
  rules: MisconceptionRule[];
}

function SubjectWorkspace({ subject }: { subject: Subject }) {
  const data = useAsync<SubjectData>(`subject:${subject.id}`, async () => {
    const [graph, unclassified, rules] = await Promise.all([
      apiFetch<TopicGraphResponse>(`/subjects/${subject.id}/topic-graph`),
      apiFetch<UnclassifiedChunk[]>(`/subjects/${subject.id}/unclassified`),
      apiFetch<{ rules: MisconceptionRule[] }>(`/subjects/${subject.id}/misconception-rules`),
    ]);
    return { topics: graph.topics, unclassified, rules: rules.rules };
  });
  const [flash, setFlash] = useState<string | null>(null);

  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />;
  if (!data.data || data.loading) {
    return (
      <Card>
        <SkeletonText lines={6} />
      </Card>
    );
  }

  return (
    <SubjectEditors
      subject={subject}
      initial={data.data}
      flash={flash}
      onSaved={(message) => {
        setFlash(message);
        data.reload();
      }}
    />
  );
}

function SubjectEditors({
  subject,
  initial,
  flash,
  onSaved,
}: {
  subject: Subject;
  initial: SubjectData;
  flash: string | null;
  onSaved: (message: string) => void;
}) {
  const [topics, setTopics] = useState<TopicNode[]>(initial.topics);
  const [editorKey, setEditorKey] = useState(0);
  const [drafting, setDrafting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [graphMsg, setGraphMsg] = useState<Message>(flash ? { tone: "success", text: flash } : null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [unclassified, setUnclassified] = useState(initial.unclassified);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [tagging, setTagging] = useState<string | null>(null);
  const [tagError, setTagError] = useState<string | null>(null);

  const [rules, setRules] = useState<MisconceptionRule[]>(initial.rules);
  const [rulesKey, setRulesKey] = useState(0);
  const [rulesDrafting, setRulesDrafting] = useState(false);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [rulesMsg, setRulesMsg] = useState<Message>(null);

  const graphDirty = JSON.stringify(topics) !== JSON.stringify(initial.topics);
  const rulesDirty = JSON.stringify(rules) !== JSON.stringify(initial.rules);

  async function handleDraft(file: File) {
    setDrafting(true);
    setGraphMsg(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiFetch<TopicGraphResponse>(`/subjects/${subject.id}/syllabus`, { method: "POST", body: form });
      setTopics(res.topics);
      setEditorKey((k) => k + 1);
      setGraphMsg({ tone: "success", text: `Drafted ${plural(res.topics.length, "topic")}. Review and edit, then confirm to save.` });
    } catch (err) {
      setGraphMsg({ tone: "danger", text: errorMessage(err, "Drafting failed.") });
    } finally {
      setDrafting(false);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    setGraphMsg(null);
    try {
      const res = await apiFetch<{ topic_count: number }>(`/subjects/${subject.id}/topic-graph`, { method: "PUT", body: { topics } });
      onSaved(`Saved ${plural(res.topic_count, "topic")}.`);
    } catch (err) {
      setGraphMsg({ tone: "danger", text: errorMessage(err, "Couldn't save the topic graph.") });
      setConfirming(false);
    }
  }

  async function tagChunk(chunkId: string) {
    const topic = assignments[chunkId] || topics[0]?.topic;
    if (!topic) return;
    setTagging(chunkId);
    setTagError(null);
    try {
      await apiFetch(`/chunks/${chunkId}/topic`, { method: "PATCH", body: { topic } });
      setUnclassified((prev) => prev.filter((c) => c.chunk_id !== chunkId));
    } catch (err) {
      setTagError(errorMessage(err, "Couldn't tag that passage."));
    } finally {
      setTagging(null);
    }
  }

  async function handleDraftRules() {
    setRulesDrafting(true);
    setRulesMsg(null);
    try {
      const res = await apiFetch<{ rules: MisconceptionRule[] }>(`/subjects/${subject.id}/misconception-rules/draft`, { method: "POST" });
      setRules(res.rules);
      setRulesKey((k) => k + 1);
      setRulesMsg({ tone: "success", text: `Drafted ${plural(res.rules.length, "rule")}. Review, then save.` });
    } catch (err) {
      setRulesMsg({ tone: "danger", text: errorMessage(err, "Drafting failed.") });
    } finally {
      setRulesDrafting(false);
    }
  }

  async function handleSaveRules() {
    setRulesSaving(true);
    setRulesMsg(null);
    try {
      const res = await apiFetch<{ rule_count: number }>(`/subjects/${subject.id}/misconception-rules`, { method: "PUT", body: { rules } });
      setRulesMsg({ tone: "success", text: `Saved ${plural(res.rule_count, "rule")}.` });
    } catch (err) {
      setRulesMsg({ tone: "danger", text: errorMessage(err, "Couldn't save rules.") });
    } finally {
      setRulesSaving(false);
    }
  }

  return (
    <>
      <Card>
        <CardHeader
          icon={<GitBranch className="h-4 w-4" />}
          title={`Topic graph · ${subject.name}`}
          description="Topics, their prerequisites and related concepts."
          actions={
            <>
              {graphDirty && <Badge tone="amber" dot>Unsaved changes</Badge>}
              <input
                ref={fileRef}
                id="syllabus-file"
                type="file"
                accept=".pdf,.pptx,.docx,.txt"
                className="sr-only"
                disabled={drafting}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleDraft(f);
                  e.target.value = "";
                }}
              />
              <Button variant="secondary" size="sm" loading={drafting} onClick={() => fileRef.current?.click()} icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}>
                {drafting ? "Drafting…" : "Draft from syllabus"}
              </Button>
            </>
          }
        />
        <p className="-mt-2 mb-4 text-xs text-tertiary">Drafting uses one AI call. Nothing is saved until you confirm.</p>

        <TopicGraphEditor key={editorKey} topics={topics} onChange={setTopics} />

        {graphMsg && <Alert tone={graphMsg.tone} className="mt-4">{graphMsg.text}</Alert>}

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-subtle pt-4">
          <Button onClick={handleConfirm} loading={confirming} disabled={topics.length === 0 || !graphDirty}>
            Confirm topic graph
          </Button>
          {graphDirty && (
            <Button
              variant="ghost"
              onClick={() => {
                setTopics(initial.topics);
                setEditorKey((k) => k + 1);
                setGraphMsg(null);
              }}
            >
              Discard changes
            </Button>
          )}
          <span className="text-xs text-tertiary">{plural(topics.length, "topic")}</span>
        </div>
      </Card>

      <Card>
        <CardHeader
          icon={<FileSearch className="h-4 w-4" />}
          title="Unclassified content"
          description="Passages that didn't match a topic during indexing. Assign each one so it shows up in the right place."
          actions={unclassified.length > 0 ? <Badge tone="amber">{unclassified.length} to review</Badge> : undefined}
        />
        {tagError && <Alert tone="danger" className="mb-3">{tagError}</Alert>}
        {unclassified.length === 0 ? (
          <EmptyState compact icon={<Tag className="h-5 w-5" />} title="Everything is classified" description="New uploads that don't match a topic will appear here." />
        ) : topics.length === 0 ? (
          <p className="text-sm text-tertiary">Add topics above before assigning passages.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {unclassified.map((c) => (
              <li key={c.chunk_id} className="rounded-lg border border-subtle p-4">
                <p className="text-xs text-tertiary">
                  {c.document_title} · Unit {c.unit ?? "—"} · Ch {c.chapter ?? "—"}
                </p>
                <p className="mt-1.5 line-clamp-4 text-sm text-secondary">{c.text_preview}…</p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
                  <Select
                    label="Assign to topic"
                    srOnlyLabel
                    value={assignments[c.chunk_id] ?? topics[0]?.topic ?? ""}
                    onChange={(e) => setAssignments((prev) => ({ ...prev, [c.chunk_id]: e.target.value }))}
                    wrapperClassName="sm:w-64"
                  >
                    {topics.map((t) => (
                      <option key={t.topic} value={t.topic}>{t.topic}</option>
                    ))}
                  </Select>
                  <Button variant="secondary" loading={tagging === c.chunk_id} disabled={tagging !== null} onClick={() => tagChunk(c.chunk_id)}>
                    Assign topic
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {topics.length > 0 && (
        <Card>
          <CardHeader
            icon={<ShieldAlert className="h-4 w-4" />}
            title="Misconception rules"
            description="Keyword rules that log a misconception when a wrong answer matches, at zero AI cost. Anything unmatched falls back to the AI check."
            actions={
              <>
                {rulesDirty && <Badge tone="amber" dot>Unsaved</Badge>}
                <Button variant="secondary" size="sm" loading={rulesDrafting} onClick={handleDraftRules} icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}>
                  Draft from topics
                </Button>
              </>
            }
          />
          <MisconceptionRulesEditor key={rulesKey} topics={topics} rules={rules} onChange={setRules} />
          {rulesMsg && <Alert tone={rulesMsg.tone} className="mt-4">{rulesMsg.text}</Alert>}
          <div className="mt-5 border-t border-subtle pt-4">
            <Button onClick={handleSaveRules} loading={rulesSaving} disabled={!rulesDirty}>
              Save rules
            </Button>
          </div>
        </Card>
      )}
    </>
  );
}
