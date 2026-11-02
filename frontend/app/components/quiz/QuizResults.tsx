import { useState } from "react";
import type { QuizAttemptResult, QuizDetail, TopicQuizPrepContext } from "../../lib/types";
import { Card, CardHeader } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { ProgressBar, masteryTone } from "../ui/Stat";
import { ProgressRing } from "../ui/DataVisualizations";
import { Button } from "../ui/Button";
import { Flag } from "lucide-react";
import { ReportQuestionDialog } from "./ReportQuestionDialog";
import { TopicQuizPrepModal } from "./TopicQuizPrepModal";
import { cn } from "../../lib/cn";
import { percent } from "../../lib/format";

function verdict(score: number): { title: string; tone: string } {
  if (score >= 80) return { title: "Excellent mastery", tone: "text-green" };
  if (score >= 60) return { title: "Solid comprehension", tone: "text-ink" };
  if (score >= 40) return { title: "Progressing steadily", tone: "text-warning" };
  return { title: "Concept review recommended", tone: "text-red" };
}

function formatAnswer(ans: string | string[] | null | undefined): string {
  if (ans == null) return "—";
  if (Array.isArray(ans)) {
    return ans.length === 0 ? "—" : ans.join(", ");
  }
  if (typeof ans === "string") {
    const trimmed = ans.trim();
    if (trimmed === "") return "—";
    if (trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (Array.isArray(parsed)) {
          return parsed.length === 0 ? "—" : parsed.join(", ");
        }
      } catch {
        // parsing failed, fall through to string return
      }
    }
    return ans;
  }
  return String(ans);
}

export function QuizResults({ result, quiz }: { result: QuizAttemptResult; quiz: QuizDetail | null }) {
  const [reportingQuestionId, setReportingQuestionId] = useState<string | null>(null);
  const [prepContext, setPrepContext] = useState<TopicQuizPrepContext | null>(null);
  const correctCount = result.results.filter((r) => r.correct).length;
  const partialCount = result.results.filter((r) => !r.correct && (r.earned_points ?? 0) > 0).length;
  const scoreRatio = result.score_ratio ?? (result.score != null ? result.score / 100 : 0);
  const v = verdict(scoreRatio * 100);
  const questionMap = new Map(quiz?.questions.map((q) => [q.id, q]) ?? []);
  const classId = result.class_id || quiz?.class_id;

  const totalPointsPossible = result.results.reduce((acc, r) => acc + (r.points_possible ?? 1.0), 0);
  const totalEarnedPoints = result.results.reduce((acc, r) => acc + (r.earned_points ?? (r.correct ? (r.points_possible ?? 1.0) : 0)), 0);

  return (
    <div className="flex flex-col gap-6">
      {/* Score Summary Panel */}
      <div className="rounded-[2px] border border-line bg-surface p-6 sm:p-8">
        <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
          <ProgressRing
            value={scoreRatio}
            size={116}
            strokeWidth={9}
          />
          <div>
            <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-1">
              [ ATTEMPT EVALUATION ]
            </div>
            <h2 className={cn("font-serif text-3xl sm:text-4xl leading-tight font-normal", v.tone)}>{v.title}</h2>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-muted">
              Earned {totalEarnedPoints.toFixed(1)} of {totalPointsPossible.toFixed(1)} points ({correctCount} of {result.results.length} fully correct{partialCount > 0 ? `, ${partialCount} partial credit` : ""}).
            </p>
            <p className="mt-1.5 font-sans text-xs text-muted">
              Your topic mastery scores and adaptive curriculum recommendations have been calibrated.
            </p>
          </div>
        </div>
      </div>

      {/* Topic Mastery Changes */}
      {Object.keys(result.topic_scores).length > 0 && (
        <Card>
          <CardHeader
            bracket="TOPIC CALIBRATION"
            title="Performance by Topic"
            description="Attempt score and updated estimated syllabus mastery."
          />
          <ul className="flex flex-col gap-4 divide-y divide-line/40">
            {Object.entries(result.topic_scores).map(([topic, rawScore]) => {
              const mastery = result.updated_mastery[topic];
              const scorePct = Math.round(rawScore * 100);
              const isWeak = rawScore < 0.60;
              return (
                <li key={topic} className="pt-3 first:pt-0">
                  <div className="mb-2 flex items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-wider">
                    <span className="truncate font-semibold text-ink">{topic}</span>
                    <span className="flex shrink-0 items-center gap-3">
                      {mastery && (
                        <span className="text-muted">
                          MASTERY: {percent(mastery.mastery_score)} ({mastery.trend.replace("_", " ")})
                        </span>
                      )}
                      <Badge tone={masteryTone(rawScore)}>Score: {scorePct}%</Badge>
                      {Boolean(classId && isWeak) && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setPrepContext({
                            topic,
                            class_id: classId,
                            mastery_score: rawScore,
                          })}
                          className="text-[10px] h-6 px-2 py-0 border-accent-red/40 text-accent-red hover:bg-accent-red/10"
                        >
                          Practice this topic
                        </Button>
                      )}
                    </span>
                  </div>
                  <ProgressBar value={rawScore} label={`${topic} score`} />
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      {/* Question Review & Explanations */}
      <Card>
        <CardHeader bracket="REVIEW" title="Question Review &amp; Explanations" />
        <ol className="flex flex-col divide-y divide-line">
          {result.results.map((r, i) => {
            const q = questionMap.get(r.question_id);
            return (
              <li key={r.question_id} className="py-5 first:pt-2 last:pb-2">
                <div className="flex items-start justify-between gap-3 font-mono text-[9px] uppercase tracking-wider text-muted mb-2">
                  <span>ITEM {String(i + 1).padStart(2, "0")} / {r.correct ? "CORRECT" : "NEEDS REVIEW"}</span>
                  <span className={r.correct ? "text-green" : "text-red"}>
                    {r.correct ? "✓ FULL CREDIT" : "✗ INCORRECT"}
                  </span>
                </div>

                <h4 className="font-serif text-xl text-ink leading-snug">
                  {q?.question_text || `Question ${i + 1}`}
                </h4>

                <div className="mt-3 flex flex-col gap-1.5 font-mono text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-muted text-[10px]">YOUR ANSWER:</span>
                    <span className={cn("px-2 py-0.5 rounded-[2px] border", r.correct ? "border-green/40 text-green bg-green/5" : "border-red/40 text-red bg-red/5")}>
                      {formatAnswer(r.chosen)}
                    </span>
                  </div>
                  {!r.correct && (
                    <div className="flex items-center gap-2">
                      <span className="text-muted text-[10px]">CORRECT ANSWER:</span>
                      <span className="px-2 py-0.5 rounded-[2px] border border-green/40 text-green bg-green/5">
                        {formatAnswer(r.correct_answer)}
                      </span>
                    </div>
                  )}
                  {Boolean(r.explanation && r.explanation.trim()) && (
                    <div className="mt-2 p-3 border border-line bg-surface2 font-sans text-xs text-muted leading-relaxed">
                      <b className="font-mono text-[9px] uppercase text-ink block mb-1">Explanation:</b>
                      {r.explanation}
                    </div>
                  )}
                  {(q?.source_document_name || q?.document_name || q?.source_page_number != null || q?.page != null || q?.section_heading || q?.snippet) && (
                    <details className="mt-2 rounded-[2px] border border-line/60 bg-surface2/60 px-2.5 py-2 font-mono text-[10px] text-muted">
                      <summary className="cursor-pointer list-none">
                        <span className="uppercase text-ink font-semibold">Source:</span>{" "}
                        {q?.document_name || q?.source_document_name || "Curriculum Document"}
                        {(q?.page != null || q?.source_page_number != null) && (
                          <> · p.{q?.page ?? q?.source_page_number}</>
                        )}
                        {q?.section_heading && (
                          <> · {q.section_heading}</>
                        )}
                      </summary>
                      {q?.snippet && (
                        <p className="mt-2 border-t border-line/40 pt-2 text-[10px] text-muted italic">
                          “{q.snippet}”
                        </p>
                      )}
                    </details>
                  )}
                  <div className="mt-2 flex justify-end">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setReportingQuestionId(r.question_id)}
                      icon={<Flag className="h-3 w-3 text-muted" />}
                      className="text-[11px] text-muted hover:text-ink"
                    >
                      Report a problem
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </Card>

      {reportingQuestionId && (
        <ReportQuestionDialog
          questionId={reportingQuestionId}
          open={Boolean(reportingQuestionId)}
          onClose={() => setReportingQuestionId(null)}
        />
      )}

      {prepContext && (
        <TopicQuizPrepModal
          open={Boolean(prepContext)}
          onClose={() => setPrepContext(null)}
          context={prepContext}
        />
      )}
    </div>
  );
}
