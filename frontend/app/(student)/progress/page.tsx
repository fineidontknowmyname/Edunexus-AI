"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../../lib/api";
import type { DashboardResponse } from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { LearningGraph } from "../../components/progress/LearningGraph";

export default function ProgressPage() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<DashboardResponse>("/progress/dashboard")
      .then(setDashboard)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load progress."));
  }, []);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!dashboard) return <p className="text-sm text-tertiary">Loading…</p>;

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-primary">Progress</h1>

      <Card>
        <div className="flex items-center gap-6">
          <div>
            <div className="text-3xl font-bold text-primary">{dashboard.engagement.current_streak}</div>
            <div className="text-xs text-tertiary">day streak</div>
          </div>
          <div>
            <div className="text-3xl font-bold text-primary">{dashboard.engagement.longest_streak}</div>
            <div className="text-xs text-tertiary">longest streak</div>
          </div>
          {dashboard.engagement.staleness_flag && (
            <Badge tone="amber">Welcome back — it's been a while</Badge>
          )}
        </div>
      </Card>

      {dashboard.upcoming_focus && (
        <Card>
          <h2 className="font-semibold text-primary mb-2">Upcoming assessment</h2>
          <p className="text-sm text-primary">
            {dashboard.upcoming_focus.assessment_name} — in {dashboard.upcoming_focus.days_remaining} day
            {dashboard.upcoming_focus.days_remaining === 1 ? "" : "s"}
          </p>
          {dashboard.upcoming_focus.weak_topics_in_scope.length > 0 && (
            <p className="text-sm text-warning mt-1">
              Weak topics in scope: {dashboard.upcoming_focus.weak_topics_in_scope.join(", ")}
            </p>
          )}
        </Card>
      )}

      {dashboard.stale_topics.length > 0 && (
        <Card>
          <h2 className="font-semibold text-primary mb-2">Not reviewed in 7+ days</h2>
          <div className="flex flex-wrap gap-2">
            {dashboard.stale_topics.map((t) => (
              <Badge key={t} tone="amber">{t}</Badge>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <h2 className="font-semibold text-primary mb-3">Mastery by topic</h2>
        <LearningGraph mastery={dashboard.mastery} />
      </Card>
    </div>
  );
}
