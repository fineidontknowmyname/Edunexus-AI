"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { TopicNode } from "../../lib/types";
import { Button } from "../ui/Button";
import { controlClasses } from "../ui/Input";
import { cn } from "../../lib/cn";

interface Props {
  topics: TopicNode[];
  onChange: (topics: TopicNode[]) => void;
}

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

const fieldLabel = "mb-1 block text-xs font-medium text-tertiary md:sr-only";
const control = cn(controlClasses, "border-strong px-2.5 py-1.5");

export function TopicGraphEditor({ topics, onChange }: Props) {
  const [newTopic, setNewTopic] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const names = new Set(topics.map((t) => t.topic.trim().toLowerCase()));

  function update(index: number, patch: Partial<TopicNode>) {
    onChange(topics.map((t, i) => (i === index ? { ...t, ...patch } : t)));
  }

  function listValue(index: number, field: "requires" | "related_concepts") {
    const key = `${index}:${field}`;
    return drafts[key] ?? topics[index][field].join(", ");
  }

  function setList(index: number, field: "requires" | "related_concepts", value: string) {
    setDrafts((prev) => ({ ...prev, [`${index}:${field}`]: value }));
    update(index, { [field]: parseList(value) } as Partial<TopicNode>);
  }

  function remove(index: number) {
    setDrafts({});
    onChange(topics.filter((_, i) => i !== index));
  }

  function add() {
    const name = newTopic.trim();
    if (!name || names.has(name.toLowerCase())) return;
    onChange([...topics, { topic: name, description: "", requires: [], related_concepts: [] }]);
    setNewTopic("");
  }

  const duplicate = newTopic.trim() !== "" && names.has(newTopic.trim().toLowerCase());

  return (
    <div className="flex flex-col gap-3">
      {topics.length > 0 && (
        <div className="hidden grid-cols-[minmax(0,11rem)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)_2.25rem] gap-3 px-3 text-xs font-medium uppercase tracking-wide text-tertiary md:grid">
          <span>Topic</span>
          <span>Description</span>
          <span>Requires</span>
          <span>Related</span>
          <span className="sr-only">Actions</span>
        </div>
      )}
      <ol className="flex flex-col gap-2">
        {topics.map((t, i) => {
          const unknown = t.requires.filter((r) => !names.has(r.toLowerCase()));
          const base = `topic-${i}`;
          return (
            <li
              key={i}
              className="grid gap-3 rounded-lg border border-subtle bg-surface-muted/30 p-3 md:grid-cols-[minmax(0,11rem)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)_2.25rem] md:items-start"
            >
              <div>
                <label htmlFor={`${base}-name`} className={fieldLabel}>Topic</label>
                <input id={`${base}-name`} className={cn(control, "font-medium")} value={t.topic} onChange={(e) => update(i, { topic: e.target.value })} />
              </div>
              <div>
                <label htmlFor={`${base}-desc`} className={fieldLabel}>Description</label>
                <textarea
                  id={`${base}-desc`}
                  className={cn(control, "min-h-[2.25rem] resize-y")}
                  rows={3}
                  value={t.description ?? ""}
                  onChange={(e) => update(i, { description: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor={`${base}-req`} className={fieldLabel}>Requires (comma-separated)</label>
                <input
                  id={`${base}-req`}
                  className={cn(control, unknown.length > 0 && "border-warning")}
                  value={listValue(i, "requires")}
                  placeholder="None"
                  aria-describedby={unknown.length > 0 ? `${base}-req-warn` : undefined}
                  onChange={(e) => setList(i, "requires", e.target.value)}
                />
                {unknown.length > 0 && (
                  <p id={`${base}-req-warn`} className="mt-1 text-xs text-warning">
                    Not a topic: {unknown.join(", ")}
                  </p>
                )}
              </div>
              <div>
                <label htmlFor={`${base}-rel`} className={fieldLabel}>Related (comma-separated)</label>
                <input
                  id={`${base}-rel`}
                  className={control}
                  value={listValue(i, "related_concepts")}
                  placeholder="None"
                  onChange={(e) => setList(i, "related_concepts", e.target.value)}
                />
              </div>
              <Button variant="ghost" size="icon" aria-label={`Remove ${t.topic || "topic"}`} onClick={() => remove(i)} className="justify-self-end hover:text-danger">
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </li>
          );
        })}
      </ol>
      {topics.length === 0 && (
        <p className="rounded-lg border border-dashed border-strong px-4 py-6 text-center text-sm text-tertiary">
          No topics yet. Upload a syllabus to draft them, or add one below.
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="flex-1">
          <label htmlFor="new-topic" className="sr-only">New topic name</label>
          <input
            id="new-topic"
            className={cn(controlClasses, "h-10 border-strong px-3", duplicate && "border-warning")}
            placeholder="Add a topic by hand"
            value={newTopic}
            onChange={(e) => setNewTopic(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          {duplicate && <p className="mt-1 text-xs text-warning">That topic already exists.</p>}
        </div>
        <Button variant="secondary" onClick={add} disabled={!newTopic.trim() || duplicate} icon={<Plus className="h-4 w-4" aria-hidden />}>
          Add topic
        </Button>
      </div>
    </div>
  );
}
