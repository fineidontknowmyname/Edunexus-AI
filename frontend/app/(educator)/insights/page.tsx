"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "../../lib/api";
import type {
  AtRiskStudent,
  ClassContextResponse,
  ClassInsightsResponse,
  ClassRow,
  FlaggedMessage,
  TrendingTopic,
} from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";

function masteryTone(avg: number): "red" | "amber" | "green" {
  if (avg >= 0.7) return "green";
  if (avg >= 0.4) return "amber";
  return "red";
}

export default function InsightsPage() {
  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [classId, setClassId] = useState("");

  const [insights, setInsights] = useState<ClassInsightsResponse | null>(null);
  const [atRisk, setAtRisk] = useState<AtRiskStudent[]>([]);
  const [trending, setTrending] = useState<TrendingTopic[]>([]);
  const [flags, setFlags] = useState<FlaggedMessage[]>([]);
  const [loading, setLoading] = useState(false);

  const [assessmentName, setAssessmentName] = useState("");
  const [assessmentDate, setAssessmentDate] = useState("");
  const [assessmentCovers, setAssessmentCovers] = useState("");
  const [savingAssessment, setSavingAssessment] = useState(false);
  const [refreshingConfusion, setRefreshingConfusion] = useState(false);

  const subjectId = classes.find((c) => c.id === classId)?.subject_id ?? null;

  useEffect(() => {
    apiFetch<ClassRow[]>("/classes/").then((rows) => {
      setClasses(rows);
      if (rows.length > 0) setClassId(rows[0].id);
    });
  }, []);

  useEffect(() => {
    if (!classId) return;
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classId]);

  async function loadAll() {
    setLoading(true);
    try {
      const [insightsRes, atRiskRes, trendingRes, flagsRes] = await Promise.all([
        apiFetch<ClassInsightsResponse>(`/insights/class/${classId}`),
        apiFetch<AtRiskStudent[]>(`/insights/students/at-risk?class_id=${classId}`),
        apiFetch<TrendingTopic[]>(`/insights/questions/trending?class_id=${classId}`),
        apiFetch<FlaggedMessage[]>(`/insights/flags?class_id=${classId}`),
      ]);
      setInsights(insightsRes);
      setAtRisk(atRiskRes);
      setTrending(trendingRes);
      setFlags(flagsRes);
    } finally {
      setLoading(false);
    }
  }

  async function handleRefreshConfusion() {
    if (!subjectId) return;
    setRefreshingConfusion(true);
    try {
      await apiFetch(`/reflections/cluster?class_id=${classId}&subject_id=${subjectId}`, { method: "POST" });
      await loadAll();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to refresh class confusion.");
    } finally {
      setRefreshingConfusion(false);
    }
  }

  async function handleScheduleAssessment(e: FormEvent) {
    e.preventDefault();
    setSavingAssessment(true);
    try {
      const existing = await apiFetch<ClassContextResponse>(`/context/class/${classId}`);
      const covers = assessmentCovers.split(",").map((s) => s.trim()).filter(Boolean);
      const assessments = [...existing.assessments, { name: assessmentName, date: assessmentDate, covers }];
      await apiFetch(`/context/class/${classId}/assessments`, {
        method: "PATCH",
        body: { assessments },
      });
      setAssessmentName("");
      setAssessmentDate("");
      setAssessmentCovers("");
      await loadAll();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to schedule assessment.");
    } finally {
      setSavingAssessment(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-primary">Class Insights</h1>

      {classes.length > 1 && (
        <select
          className="w-full px-3 py-2 border border-strong rounded-md text-sm bg-surface text-primary"
          value={classId}
          onChange={(e) => setClassId(e.target.value)}
        >
          {classes.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      )}

      {loading && <p className="text-sm text-tertiary">Loading…</p>}

      <Card>
        <h2 className="font-semibold text-primary mb-3">Schedule an assessment</h2>
        <form onSubmit={handleScheduleAssessment} className="flex flex-col gap-3">
          <Input label="Name" value={assessmentName} onChange={(e) => setAssessmentName(e.target.value)} required />
          <Input label="Date" type="date" value={assessmentDate} onChange={(e) => setAssessmentDate(e.target.value)} required />
          <Input
            label="Topics covered (comma-separated)"
            value={assessmentCovers}
            onChange={(e) => setAssessmentCovers(e.target.value)}
            placeholder="SJF, Round Robin, FCFS"
          />
          <Button type="submit" loading={savingAssessment}>Schedule</Button>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Mastery heatmap</h2>
        {!insights || insights.heatmap.length === 0 ? (
          <p className="text-sm text-tertiary">No quiz data yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {insights.heatmap.map((h) => (
              <div key={h.topic} className="flex items-center justify-between text-sm">
                <span className="text-primary">{h.topic}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-tertiary">{h.student_count} student{h.student_count === 1 ? "" : "s"}</span>
                  {h.struggling_count > 0 && (
                    <span className="text-xs text-danger">{h.struggling_count} struggling</span>
                  )}
                  <Badge tone={masteryTone(h.average_mastery)}>{Math.round(h.average_mastery * 100)}%</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Common misconceptions</h2>
        {!insights || insights.misconceptions.length === 0 ? (
          <p className="text-sm text-tertiary">None detected yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {insights.misconceptions.map((m, i) => (
              <div key={i} className="text-sm">
                <span className="font-medium text-primary">{m.topic}</span>
                <span className="text-secondary"> — {m.description} </span>
                <Badge tone="amber">{m.count}×</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">At-risk students</h2>
        {atRisk.length === 0 ? (
          <p className="text-sm text-tertiary">No at-risk students — or no assessment scheduled yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {atRisk.map((s) => (
              <div key={s.student_id} className="flex items-center justify-between text-sm">
                <div>
                  <Link href={`/students/${s.student_id}?class_id=${classId}`} className="text-accent-secondary hover:underline font-medium">
                    {s.full_name}
                  </Link>
                  <span className="text-tertiary"> — weak on {s.weak_topics_in_scope.join(", ")}</span>
                </div>
                <Badge tone="red">{s.days_remaining}d left</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-primary">Class confusion</h2>
          <Button
            variant="secondary"
            onClick={handleRefreshConfusion}
            loading={refreshingConfusion}
            disabled={!subjectId}
          >
            Refresh
          </Button>
        </div>
        {!subjectId ? (
          <p className="text-sm text-tertiary">This class has no subject set yet.</p>
        ) : !insights || insights.class_confusion.length === 0 ? (
          <p className="text-sm text-tertiary">
            No confusion clusters yet — refresh once students have submitted a few reflections.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {insights.class_confusion.map((c, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="text-secondary">{c.representative_text}</span>
                <Badge tone="blue">{c.cluster_size} student{c.cluster_size === 1 ? "" : "s"}</Badge>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Trending topics (last 7 days)</h2>
        {trending.length === 0 ? (
          <p className="text-sm text-tertiary">No recent activity.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {trending.map((t) => (
              <Badge key={t.topic} tone="blue">{t.topic} · {t.questions_asked}</Badge>
            ))}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold text-primary mb-3">Flagged responses</h2>
        {flags.length === 0 ? (
          <p className="text-sm text-tertiary">No flagged responses.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {flags.map((f) => (
              <div key={f.message_id} className="border-t border-subtle pt-2">
                <p className="text-xs text-tertiary">{f.student_name} · {new Date(f.created_at).toLocaleString()}</p>
                <p className="text-sm text-primary">{f.content}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
