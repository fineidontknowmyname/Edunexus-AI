"use client";

import { useState } from "react";
import type { TopicNode } from "../../lib/types";
import { Button } from "../ui/Button";

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

export function TopicGraphEditor({ topics, onChange }: Props) {
  const [newTopic, setNewTopic] = useState("");

  function update(index: number, patch: Partial<TopicNode>) {
    onChange(topics.map((t, i) => (i === index ? { ...t, ...patch } : t)));
  }

  function remove(index: number) {
    onChange(topics.filter((_, i) => i !== index));
  }

  function add() {
    const name = newTopic.trim();
    if (!name || topics.some((t) => t.topic.toLowerCase() === name.toLowerCase())) return;
    onChange([...topics, { topic: name, description: "", requires: [], related_concepts: [] }]);
    setNewTopic("");
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-tertiary border-b border-subtle">
              <th className="py-2 pr-3 font-medium">Topic</th>
              <th className="py-2 pr-3 font-medium">Description</th>
              <th className="py-2 pr-3 font-medium">Requires (comma-sep)</th>
              <th className="py-2 pr-3 font-medium">Related (comma-sep)</th>
              <th className="py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {topics.map((t, i) => (
              <tr key={i} className="border-b border-subtle align-top">
                <td className="py-2 pr-3">
                  <input
                    className="w-40 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    value={t.topic}
                    onChange={(e) => update(i, { topic: e.target.value })}
                  />
                </td>
                <td className="py-2 pr-3">
                  <textarea
                    className="w-64 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    rows={2}
                    value={t.description ?? ""}
                    onChange={(e) => update(i, { description: e.target.value })}
                  />
                </td>
                <td className="py-2 pr-3">
                  <input
                    className="w-44 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    value={t.requires.join(", ")}
                    onChange={(e) => update(i, { requires: parseList(e.target.value) })}
                  />
                </td>
                <td className="py-2 pr-3">
                  <input
                    className="w-44 px-2 py-1 border border-strong rounded bg-surface text-primary"
                    value={t.related_concepts.join(", ")}
                    onChange={(e) => update(i, { related_concepts: parseList(e.target.value) })}
                  />
                </td>
                <td className="py-2">
                  <button
                    onClick={() => remove(i)}
                    className="text-xs text-danger hover:underline"
                    type="button"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
            {topics.length === 0 && (
              <tr>
                <td colSpan={5} className="py-4 text-tertiary">
                  No topics yet. Upload a syllabus to draft them, or add one below.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex gap-2">
        <input
          className="flex-1 px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary"
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
        <Button type="button" variant="secondary" onClick={add}>
          Add topic
        </Button>
      </div>
    </div>
  );
}
