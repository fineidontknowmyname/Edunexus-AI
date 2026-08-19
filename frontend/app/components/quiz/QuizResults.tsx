import type { QuizAttemptResult } from "../../lib/types";
import { Card } from "../ui/Card";
import { Badge } from "../ui/Badge";

export function QuizResults({ result }: { result: QuizAttemptResult }) {
  return (
    <Card>
      <h2 className="text-xl font-bold text-gray-900 mb-1">Score: {result.score.toFixed(0)}%</h2>
      <p className="text-sm text-gray-500 mb-4">
        {result.results.filter((r) => r.correct).length} / {result.results.length} correct
      </p>

      <h3 className="font-semibold text-gray-900 mb-2 text-sm">Topic breakdown</h3>
      <div className="flex flex-col gap-1 mb-4">
        {Object.entries(result.topic_scores).map(([topic, score]) => (
          <div key={topic} className="flex items-center justify-between text-sm">
            <span className="text-gray-700">{topic}</span>
            <Badge tone={score >= 0.7 ? "green" : score >= 0.4 ? "amber" : "red"}>
              {(score * 100).toFixed(0)}%
            </Badge>
          </div>
        ))}
      </div>

      {Object.keys(result.updated_mastery).length > 0 && (
        <>
          <h3 className="font-semibold text-gray-900 mb-2 text-sm">Updated mastery</h3>
          <div className="flex flex-col gap-1">
            {Object.entries(result.updated_mastery).map(([topic, m]) => (
              <div key={topic} className="flex items-center justify-between text-sm">
                <span className="text-gray-700">{topic}</span>
                <span className="text-gray-500">
                  {(m.mastery_score * 100).toFixed(0)}% ({m.trend})
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
