import type { DashboardMasteryEntry } from "../../lib/types";
import { MasteryBar } from "./MasteryBar";

export function LearningGraph({ mastery }: { mastery: DashboardMasteryEntry[] }) {
  if (mastery.length === 0) {
    return <p className="text-sm text-gray-500">No quiz attempts yet — take a quiz to start tracking mastery.</p>;
  }

  const sorted = [...mastery].sort((a, b) => a.score - b.score);

  return (
    <div className="flex flex-col gap-4">
      {sorted.map((m) => (
        <MasteryBar key={m.topic} topic={m.topic} score={m.score} trend={m.trend} attempts={m.attempts} />
      ))}
    </div>
  );
}
