import { CheckCircle2, XCircle } from "lucide-react";
import type { QuizAttemptResult, QuizDetail } from "../../lib/types";
import { Card, CardHeader } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { ProgressBar, masteryTone } from "../ui/Stat";
import { cn } from "../../lib/cn";

function verdict(score: number): { title: string; tone: string } {
  if (score >= 80) return { title: "Excellent work", tone: "text-success" };
  if (score >= 60) return { title: "Good effort", tone: "text-accent-secondary" };
  if (score >= 40) return { title: "Getting there", tone: "text-warning" };
  return { title: "Let's review this together", tone: "text-danger" };
}

export function QuizResults({ result, quiz }: { result: QuizAttemptResult; quiz: QuizDetail | null }) {
  const correct = result.results.filter((r) => r.correct).length;
  const v = verdict(result.score);
  const questionText = new Map(quiz?.questions.map((q) => [q.id, q.question_text]) ?? []);
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const dash = (Math.max(0, Math.min(100, result.score)) / 100) * circumference;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:text-left">
          <div className="relative h-24 w-24 shrink-0">
            <svg viewBox="0 0 80 80" className="h-24 w-24 -rotate-90" aria-hidden>
              <circle cx="40" cy="40" r={radius} fill="none" strokeWidth="8" className="stroke-surface-muted" />
              <circle
                cx="40"
                cy="40"
                r={radius}
                fill="none"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={`${dash} ${circumference}`}
                className={cn(result.score >= 70 ? "stroke-success" : result.score >= 40 ? "stroke-warning" : "stroke-danger")}
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-xl font-semibold tabular-nums text-primary">
              {result.score.toFixed(0)}%
            </span>
          </div>
          <div>
            <h2 className={cn("text-xl font-semibold", v.tone)}>{v.title}</h2>
            <p className="mt-1 text-sm text-tertiary">
              You got {correct} of {result.results.length} questions right. Your mastery and learning path have been updated.
            </p>
          </div>
        </div>
      </Card>

      {Object.keys(result.topic_scores).length > 0 && (
        <Card>
          <CardHeader title="By topic" description="This attempt, and your updated mastery." />
          <ul className="flex flex-col gap-4">
            {Object.entries(result.topic_scores).map(([topic, score]) => {
              const mastery = result.updated_mastery[topic];
              return (
                <li key={topic}>
                  <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                    <span className="truncate font-medium text-primary">{topic}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      {mastery && <span className="text-xs text-tertiary">Mastery {Math.round(mastery.mastery_score * 100)}% · {mastery.trend.replace("_", " ")}</span>}
                      <Badge tone={masteryTone(score)}>{Math.round(score * 100)}%</Badge>
                    </span>
                  </div>
                  <ProgressBar value={score} label={`${topic} score`} />
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader title="Review answers" />
        <ol className="flex flex-col divide-y divide-subtle">
          {result.results.map((r, i) => (
            <li key={r.question_id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              {r.correct ? (
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-label="Correct" />
              ) : (
                <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-label="Incorrect" />
              )}
              <div className="min-w-0 text-sm">
                <p className="font-medium text-primary">
                  {i + 1}. {questionText.get(r.question_id) ?? "Question"}
                </p>
                {r.correct ? (
                  <p className="mt-0.5 text-success">{r.chosen}</p>
                ) : (
                  <div className="mt-0.5 flex flex-col gap-0.5">
                    <p className="text-danger">
                      <span className="text-tertiary">Your answer: </span>
                      {r.chosen ?? "No answer"}
                    </p>
                    <p className="text-success">
                      <span className="text-tertiary">Correct: </span>
                      {r.correct_answer}
                    </p>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
