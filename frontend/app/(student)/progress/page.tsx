"use client";

import { BarChart3, CalendarClock, Clock, Flame, Trophy } from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import { percent, plural } from "../../lib/format";
import type { ClassRow, DashboardResponse } from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Alert, ErrorState, PageSkeleton } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { StatCard } from "../../components/ui/Stat";
import { StudentClassGate } from "../../components/layout/StudentClassGate";
import { LearningGraph } from "../../components/progress/LearningGraph";

export default function ProgressPage() {
  return <StudentClassGate>{(activeClass, picker) => <Progress key={activeClass.id} activeClass={activeClass} picker={picker} />}</StudentClassGate>;
}

function Progress({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const dashboard = useApi<DashboardResponse>(`/progress/dashboard?class_id=${activeClass.id}`);

  if (dashboard.error) {
    return (
      <PageContainer>
        <PageHeader title="Progress" />
        <ErrorState message={dashboard.error} onRetry={dashboard.reload} />
      </PageContainer>
    );
  }
  if (!dashboard.data) {
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  }

  const d = dashboard.data;
  const avg = d.mastery.length > 0 ? d.mastery.reduce((s, m) => s + m.score, 0) / d.mastery.length : null;
  const strong = d.mastery.filter((m) => m.score >= 0.7).length;

  return (
    <PageContainer>
      <PageHeader title="Progress" description={`Your mastery and activity in ${activeClass.name}.`} actions={picker()} />

      {d.engagement.staleness_flag && (
        <Alert tone="info" title="Welcome back">
          It&apos;s been a few days. A short quiz is a great way to get back into it.
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Avg mastery" value={avg === null ? "—" : percent(avg)} icon={<BarChart3 className="h-4 w-4" />} hint={plural(d.mastery.length, "topic")} />
        <StatCard label="Strong topics" value={strong} icon={<Trophy className="h-4 w-4" />} hint="70% or higher" tone={strong > 0 ? "success" : "default"} />
        <StatCard label="Day streak" value={d.engagement.current_streak} icon={<Flame className="h-4 w-4" />} hint="days in a row" />
        <StatCard label="Longest streak" value={d.engagement.longest_streak} icon={<Flame className="h-4 w-4" />} hint="personal best" />
      </div>

      {(d.upcoming_focus || d.stale_topics.length > 0) && (
        <div className="grid gap-6 md:grid-cols-2">
          {d.upcoming_focus && (
            <Card>
              <CardHeader icon={<CalendarClock className="h-4 w-4" />} title="Upcoming assessment" />
              <p className="font-semibold text-primary">{d.upcoming_focus.assessment_name}</p>
              <p className="text-sm text-tertiary">in {plural(d.upcoming_focus.days_remaining, "day")}</p>
              {d.upcoming_focus.weak_topics_in_scope.length > 0 && (
                <div className="mt-3">
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-warning">Weak topics in scope</p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.upcoming_focus.weak_topics_in_scope.map((t) => (
                      <Badge key={t} tone="amber">{t}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}
          {d.stale_topics.length > 0 && (
            <Card>
              <CardHeader icon={<Clock className="h-4 w-4" />} title="Due for review" description="Not reviewed in 7+ days." />
              <div className="flex flex-wrap gap-1.5">
                {d.stale_topics.map((t) => (
                  <Badge key={t} tone="gray">{t}</Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      <Card>
        <CardHeader icon={<BarChart3 className="h-4 w-4" />} title="Mastery by topic" description="Weakest topics first." />
        <LearningGraph mastery={d.mastery} />
      </Card>
    </PageContainer>
  );
}
