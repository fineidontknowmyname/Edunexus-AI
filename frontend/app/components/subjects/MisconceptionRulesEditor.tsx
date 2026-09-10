"use client";

import { useState } from "react";
import type { MisconceptionRule, TopicNode } from "../../lib/types";
import { Button } from "../ui/Button";

interface Props {
  topics: TopicNode[];
  rules: MisconceptionRule[];
  onChange: (rules: MisconceptionRule[]) => void;
}

function parseList(v: string): string[] {
  return v.split(",").map((s) => s.trim()).filter(Boolean);
}

export function MisconceptionRulesEditor({ topics, rules, onChange }: Props) {
  const [newTopic, setNewTopic] = useState("");

  function update(i: number, patch: Partial<MisconceptionRule>) {
    onChange(rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function remove(i: number) {
    onChange(rules.filter((_, idx) => idx !== i));
  }
  function add() {
    const topic = newTopic || topics[0]?.topic;
    if (!topic) return;
    onChange([
      ...rules,
      { topic, name: "", description: "", wrong_answer_keywords: [], question_keywords: [] },
    ]);
    setNewTopic("");
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-tertiary border-b border-subtle">
              <th className="py-2 pr-3 font-medium">Topic</th>
              <th className="py-2 pr-3 font-medium">Misconception</th>
              <th className="py-2 pr-3 font-medium">Wrong-answer keywords</th>
              <th className="py-2 pr-3 font-medium">Question keywords (optional)</th>
              <th className="py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r, i) => (
              <tr key={i} className="border-b border-subtle align-top">
                <td className="py-2 pr-3">
                  <select
                    className="w-36 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    value={r.topic}
                    onChange={(e) => update(i, { topic: e.target.value })}
                  >
                    {topics.map((t) => (
                      <option key={t.topic} value={t.topic}>{t.topic}</option>
                    ))}
                  </select>
                </td>
                <td className="py-2 pr-3">
                  <textarea
                    className="w-64 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    rows={2}
                    placeholder="e.g. Confuses paging with segmentation"
                    value={r.description}
                    onChange={(e) => update(i, { description: e.target.value })}
                  />
                </td>
                <td className="py-2 pr-3">
                  <input
                    className="w-44 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    placeholder="segmentation, segment"
                    value={r.wrong_answer_keywords.join(", ")}
                    onChange={(e) => update(i, { wrong_answer_keywords: parseList(e.target.value) })}
                  />
                </td>
                <td className="py-2 pr-3">
                  <input
                    className="w-44 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    placeholder="paging"
                    value={r.question_keywords.join(", ")}
                    onChange={(e) => update(i, { question_keywords: parseList(e.target.value) })}
                  />
                </td>
                <td className="py-2">
                  <button onClick={() => remove(i)} type="button" className="text-xs text-danger hover:underline">
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={5} className="py-4 text-tertiary">
                  No rules. Draft from topics, or add one — questions still fall back to the AI check.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex gap-2">
        <select
          className="px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary"
          value={newTopic}
          onChange={(e) => setNewTopic(e.target.value)}
        >
          <option value="">Add rule for…</option>
          {topics.map((t) => (
            <option key={t.topic} value={t.topic}>{t.topic}</option>
          ))}
        </select>
        <Button type="button" variant="secondary" onClick={add} disabled={topics.length === 0}>
          Add rule
        </Button>
      </div>
    </div>
  );
}
