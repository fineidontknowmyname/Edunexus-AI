import Link from "next/link";
import { BarChart3 } from "lucide-react";
import type { DashboardMasteryEntry } from "../../lib/types";
import { EmptyState } from "../ui/Feedback";
import { MasteryBar } from "./MasteryBar";

export function LearningGraph({ mastery }: { mastery: DashboardMasteryEntry[] }) {
  if (mastery.length === 0) {
    return (
      <EmptyState
        compact
        icon={<BarChart3 className="h-5 w-5" />}
        title="No quiz attempts yet"
        description="Take a quiz to start tracking your mastery by topic."
        action={
          <Link href="/quiz" className="text-sm font-medium text-accent-secondary hover:underline">
            Browse quizzes
          </Link>
        }
      />
    );
  }

  const sorted = [...mastery].sort((a, b) => a.score - b.score);

  return (
    <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
      {sorted.map((m) => (
        <MasteryBar key={m.topic} topic={m.topic} score={m.score} trend={m.trend} attempts={m.attempts} />
      ))}
    </div>
  );
}
