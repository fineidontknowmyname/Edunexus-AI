"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { MisconceptionRule, TopicNode } from "../../lib/types";
import { Button } from "../ui/Button";
import { controlClasses, Select } from "../ui/Input";
import { cn } from "../../lib/cn";

interface Props {
  topics: TopicNode[];
  rules: MisconceptionRule[];
  onChange: (rules: MisconceptionRule[]) => void;
}

function parseList(v: string): string[] {
  return v.split(",").map((s) => s.trim()).filter(Boolean);
}

const fieldLabel = "mb-1 block text-xs font-medium text-tertiary md:sr-only";
const control = cn(controlClasses, "border-strong px-2.5 py-1.5");
const GRID = "md:grid-cols-[minmax(0,10rem)_minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)_2.25rem]";

export function MisconceptionRulesEditor({ topics, rules, onChange }: Props) {
  const [newTopic, setNewTopic] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  function update(i: number, patch: Partial<MisconceptionRule>) {
    onChange(rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function listValue(i: number, field: "wrong_answer_keywords" | "question_keywords") {
    return drafts[`${i}:${field}`] ?? rules[i][field].join(", ");
  }

  function setList(i: number, field: "wrong_answer_keywords" | "question_keywords", value: string) {
    setDrafts((prev) => ({ ...prev, [`${i}:${field}`]: value }));
    update(i, { [field]: parseList(value) } as Partial<MisconceptionRule>);
  }

  function remove(i: number) {
    setDrafts({});
    onChange(rules.filter((_, idx) => idx !== i));
  }

  function add() {
    const topic = newTopic || topics[0]?.topic;
    if (!topic) return;
    onChange([...rules, { topic, name: "", description: "", wrong_answer_keywords: [], question_keywords: [] }]);
    setNewTopic("");
  }

  return (
    <div className="flex flex-col gap-3">
      {rules.length > 0 && (
        <div className={cn("hidden gap-3 px-3 text-xs font-medium uppercase tracking-wide text-tertiary md:grid", GRID)}>
          <span>Topic</span>
          <span>Misconception</span>
          <span>Wrong-answer keywords</span>
          <span>Question keywords</span>
          <span className="sr-only">Actions</span>
        </div>
      )}
      <ol className="flex flex-col gap-2">
        {rules.map((r, i) => {
          const base = `rule-${i}`;
          return (
            <li key={i} className={cn("grid gap-3 rounded-lg border border-subtle bg-surface-muted/30 p-3 md:items-start", GRID)}>
              <div>
                <label htmlFor={`${base}-topic`} className={fieldLabel}>Topic</label>
                <select id={`${base}-topic`} className={cn(control, "h-[2.125rem]")} value={r.topic} onChange={(e) => update(i, { topic: e.target.value })}>
                  {topics.map((t) => (
                    <option key={t.topic} value={t.topic}>{t.topic}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${base}-desc`} className={fieldLabel}>Misconception</label>
                <textarea
                  id={`${base}-desc`}
                  className={cn(control, "min-h-[2.25rem] resize-y")}
                  rows={2}
                  placeholder="e.g. Confuses paging with segmentation"
                  value={r.description}
                  onChange={(e) => update(i, { description: e.target.value })}
                />
              </div>
              <div>
                <label htmlFor={`${base}-wrong`} className={fieldLabel}>Wrong-answer keywords</label>
                <input
                  id={`${base}-wrong`}
                  className={control}
                  placeholder="segmentation, segment"
                  value={listValue(i, "wrong_answer_keywords")}
                  onChange={(e) => setList(i, "wrong_answer_keywords", e.target.value)}
                />
              </div>
              <div>
                <label htmlFor={`${base}-q`} className={fieldLabel}>Question keywords (optional)</label>
                <input
                  id={`${base}-q`}
                  className={control}
                  placeholder="paging"
                  value={listValue(i, "question_keywords")}
                  onChange={(e) => setList(i, "question_keywords", e.target.value)}
                />
              </div>
              <Button variant="ghost" size="icon" aria-label={`Remove rule for ${r.topic}`} onClick={() => remove(i)} className="justify-self-end hover:text-danger">
                <Trash2 className="h-4 w-4" aria-hidden />
              </Button>
            </li>
          );
        })}
      </ol>
      {rules.length === 0 && (
        <p className="rounded-lg border border-dashed border-strong px-4 py-6 text-center text-sm text-tertiary">
          No rules yet. Draft them from your topics, or add one. Unmatched wrong answers still fall back to the AI check.
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <Select label="Add rule for topic" srOnlyLabel value={newTopic} onChange={(e) => setNewTopic(e.target.value)} wrapperClassName="sm:w-64">
          <option value="">Add rule for…</option>
          {topics.map((t) => (
            <option key={t.topic} value={t.topic}>{t.topic}</option>
          ))}
        </Select>
        <Button variant="secondary" onClick={add} disabled={topics.length === 0} icon={<Plus className="h-4 w-4" aria-hidden />}>
          Add rule
        </Button>
      </div>
    </div>
  );
}
