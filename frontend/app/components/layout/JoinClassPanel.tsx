"use client";

import { useState } from "react";
import { School } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import type { ClassRow } from "../../lib/types";
import { Button } from "../ui/Button";
import { Card, CardHeader } from "../ui/Card";
import { Alert, EmptyState, ErrorState, SkeletonText } from "../ui/Feedback";

export function JoinClassPanel({ onJoined }: { onJoined: () => void }) {
  const browse = useApi<ClassRow[]>("/classes/browse");
  const [joining, setJoining] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleJoin(classId: string) {
    setJoining(classId);
    setError(null);
    try {
      await apiFetch(`/classes/${classId}/enroll`, { method: "POST" });
      onJoined();
    } catch (err) {
      setError(errorMessage(err, "Couldn't join that class."));
    } finally {
      setJoining(null);
    }
  }

  return (
    <div className="mx-auto w-full max-w-xl">
      <Card>
        <CardHeader
          icon={<School className="h-4 w-4" />}
          title="Join a class to get started"
          description="Your tutor, quizzes and learning path are all tied to a class. Pick the one your teacher set up."
        />
        {error && <Alert tone="danger" className="mb-4">{error}</Alert>}
        {browse.error ? (
          <ErrorState message={browse.error} onRetry={browse.reload} />
        ) : !browse.data ? (
          <SkeletonText lines={3} />
        ) : browse.data.length === 0 ? (
          <EmptyState compact title="No classes available yet" description="Ask your teacher to create a class, then come back here." />
        ) : (
          <ul className="flex flex-col divide-y divide-subtle rounded-lg border border-subtle">
            {browse.data.map((c) => (
              <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-primary">{c.name}</p>
                  {c.subject && <p className="truncate text-xs text-tertiary">{c.subject}</p>}
                </div>
                <Button variant="secondary" size="sm" loading={joining === c.id} disabled={joining !== null} onClick={() => handleJoin(c.id)}>
                  Join
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
