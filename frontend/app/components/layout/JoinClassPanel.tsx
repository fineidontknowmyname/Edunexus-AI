"use client";

import { useState } from "react";
import { KeyRound, School } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import type { ClassBrowseRow } from "../../lib/types";
import { Button } from "../ui/Button";
import { Card, CardHeader } from "../ui/Card";
import { Alert, EmptyState, ErrorState, SkeletonText } from "../ui/Feedback";
import { Input } from "../ui/Input";

export function JoinClassPanel({
  onJoined,
  compact = false,
}: {
  onJoined: () => void;
  compact?: boolean;
}) {
  const browse = useApi<ClassBrowseRow[]>("/classes/browse");
  const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [joining, setJoining] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleJoin(classId: string) {
    const code = joinCode.trim();
    if (!code) {
      setError("Please enter the join code given by your teacher.");
      return;
    }
    setJoining(classId);
    setError(null);
    try {
      await apiFetch(`/classes/${classId}/enroll`, {
        method: "POST",
        body: { join_code: code },
      });
      setSelectedClassId(null);
      setJoinCode("");
      onJoined();
    } catch (err) {
      setError(errorMessage(err, "Couldn't join that class."));
    } finally {
      setJoining(null);
    }
  }

  const content = (
    <>
      {error && (
        <Alert tone="danger" className="mb-4" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}
      {browse.error ? (
        <ErrorState message={browse.error} onRetry={browse.reload} />
      ) : !browse.data ? (
        <SkeletonText lines={3} />
      ) : browse.data.length === 0 ? (
        <EmptyState
          compact
          title="No classes available to join"
          description="Ask your teacher to create a class or verify your enrollment."
        />
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-[2px] border border-line">
          {browse.data.map((c) => {
            const isSelected = selectedClassId === c.id;
            return (
              <li key={c.id} className="flex flex-col gap-2 p-4 bg-surface hover:bg-surface2 transition-colors">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-serif text-lg text-ink leading-tight">{c.name}</p>
                    {c.subject && <p className="truncate font-mono text-[9px] uppercase tracking-[0.08em] text-muted mt-0.5">{c.subject}</p>}
                  </div>
                  {!isSelected ? (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={joining !== null}
                      onClick={() => {
                        setSelectedClassId(c.id);
                        setJoinCode("");
                        setError(null);
                      }}
                    >
                      Join →
                    </Button>
                  ) : null}
                </div>

                {isSelected && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      handleJoin(c.id);
                    }}
                    className="mt-3 flex flex-col gap-2 rounded-[2px] border border-line bg-surface2 p-3.5"
                  >
                    <label
                      htmlFor={`join-code-${c.id}`}
                      className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted"
                    >
                      <KeyRound className="h-3 w-3 text-red" aria-hidden />
                      Enter teacher&apos;s join code
                    </label>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        id={`join-code-${c.id}`}
                        autoFocus
                        placeholder="e.g. 4F8A9B2C"
                        value={joinCode}
                        onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                        maxLength={12}
                        className="w-44 font-mono uppercase tracking-wider"
                      />
                      <Button
                        type="submit"
                        variant="primary"
                        size="sm"
                        loading={joining === c.id}
                        disabled={joining !== null || !joinCode.trim()}
                      >
                        Enroll
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={joining !== null}
                        onClick={() => {
                          setSelectedClassId(null);
                          setJoinCode("");
                          setError(null);
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );

  if (compact) {
    return <div className="w-full">{content}</div>;
  }

  return (
    <div className="mx-auto w-full max-w-xl">
      <Card>
        <CardHeader
          icon={<School className="h-4 w-4" />}
          title="Join a class to get started"
          description="Your tutor, quizzes and learning path are all tied to a class. Pick your class and enter your teacher's code."
        />
        {content}
      </Card>
    </div>
  );
}
