"use client";

import { BarChart3, CalendarClock, Clock, Flame, Target } from "lucide-react";
import { useApi } from "../../lib/hooks/useApi";
import { percent, plural } from "../../lib/format";
import type { ClassRow, DashboardResponse } from "../../lib/types";
import { Card, CardHeader, CardTakeaway } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Alert, ErrorState, PageSkeleton } from "../../components/ui/Feedback";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { StatCard } from "../../components/ui/Stat";
import { StudentClassGate } from "../../components/layout/StudentClassGate";
import { LearningGraph } from "../../components/progress/LearningGraph";
import { RecommendedLearningSection } from "../../components/progress/RecommendedLearningSection";
import { DonutChart, type DonutSegment } from "../../components/ui/DataVisualizations";

export default function ProgressPage() {
  return (
    <StudentClassGate>
      {(activeClass, picker) => <Progress key={activeClass.id} activeClass={activeClass} picker={picker} />}
    </StudentClassGate>
  );
}

function Progress({ activeClass, picker }: { activeClass: ClassRow; picker: (className?: string) => React.ReactNode }) {
  const dashboard = useApi<DashboardResponse>(`/progress/dashboard?class_id=${activeClass.id}`);

  if (dashboard.error) {
    return (
      <PageContainer>
        <PageHeader title="Estimated Subject Progress" />
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
  const summary = d.summary;
  const avg = summary?.assessed_average ?? (d.mastery.length > 0 ? d.mastery.reduce((s, m) => s + m.score, 0) / d.mastery.length : null);
  const totalSyllabus = summary?.total_syllabus_topics ?? d.mastery.length;
  const attemptedCount = summary?.attempted_topics ?? d.mastery.length;
  const coverageRatio = summary?.coverage_ratio ?? (totalSyllabus > 0 ? attemptedCount / totalSyllabus : 0);
  const strongCount = summary?.mastered_topics ?? d.mastery.filter((m) => m.score >= 0.7).length;
  const moderateCount = d.mastery.filter((m) => m.score >= 0.4 && m.score < 0.7).length;
  const needsReviewCount = d.mastery.filter((m) => m.score < 0.4).length;

  const donutSegments: DonutSegment[] = [
    { label: "Above 70%", count: strongCount, colorClass: "stroke-accent-green", badgeTone: "green" },
    { label: "40% - 69%", count: moderateCount, colorClass: "stroke-ink/40", badgeTone: "gray" },
    { label: "Below 40%", count: needsReviewCount, colorClass: "stroke-accent-red", badgeTone: "red" },
  ];

  return (
    <PageContainer>
      <PageHeader
        eyebrow="[ 03 / ESTIMATES ]"
        title="Estimated Subject Progress"
        description={`Evaluated topic estimates and activity in ${activeClass.name}.`}
        actions={picker()}
      />

      {d.engagement.staleness_flag && (
        <Alert tone="info" title="Welcome back">
          It&apos;s been a few days since your last activity. Taking a quick diagnostic quiz will calibrate your progress.
        </Alert>
      )}

      {/* Metrics Row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          variant="highlight"
          label="Assessed Avg Score"
          value={avg === null ? "—" : percent(avg)}
          icon={<BarChart3 className="h-5 w-5" />}
          hint={totalSyllabus > 0 ? `${attemptedCount}/${totalSyllabus} topics (${percent(coverageRatio)} coverage)` : `${plural(attemptedCount, "topic")} assessed across syllabus`}
        />
        <StatCard
          label="Tracking 70%+"
          value={strongCount}
          icon={<Target className="h-5 w-5" />}
          hint="above target threshold"
          tone={strongCount > 0 ? "success" : "default"}
        />
        <StatCard
          label="Active Day Streak"
          value={d.engagement.current_streak}
          icon={<Flame className="h-5 w-5" />}
          hint={`in ${activeClass.name}`}
        />
        <StatCard
          label="Longest Streak"
          value={d.engagement.longest_streak}
          icon={<Flame className="h-5 w-5" />}
          hint={`best in ${activeClass.name}`}
        />
      </div>

      {/* Topic Distribution & Focus Row */}
      <div className="grid gap-6 md:grid-cols-3 mt-6">
        {/* Donut Chart Card */}
        <Card className="flex flex-col justify-between">
          <CardHeader
            showDot
            title="Topic Distribution"
            description="Breakdown of estimated performance bands"
          />
          <div className="py-2">
            <DonutChart
              segments={donutSegments}
              centerTitle={d.mastery.length.toString()}
              centerSubtitle="Assessed"
            />
          </div>
          <CardTakeaway
            text={`${strongCount} of ${attemptedCount} assessed topics currently estimated at or above 70% (${percent(coverageRatio)} syllabus coverage).`}
          />
        </Card>

        {/* Assessment Focus / Stale Topics */}
        <div className="md:col-span-2 flex flex-col gap-6">
          {d.upcoming_focus && (
            <Card>
              <CardHeader showDot icon={<CalendarClock className="h-4 w-4" />} title="Upcoming Assessment Focus" />
              <p className="font-serif text-[18px] text-ink">{d.upcoming_focus.assessment_name}</p>
              <p className="text-xs font-mono uppercase tracking-[0.06em] text-muted mt-1">
                Scheduled in {plural(d.upcoming_focus.days_remaining, "day")} · {plural(d.upcoming_focus.topics_in_scope.length, "topic")} in syllabus scope
              </p>
              {d.upcoming_focus.weak_topics_in_scope.length > 0 && (
                <div className="mt-3.5">
                  <p className="mb-2 text-[11px] font-mono uppercase tracking-[0.06em] text-accent-red font-semibold">
                    Priority focus topics before test:
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {d.upcoming_focus.weak_topics_in_scope.map((t) => (
                      <Badge key={t} tone="red">{t}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          )}

          {d.stale_topics.length > 0 && (
            <Card>
              <CardHeader showDot icon={<Clock className="h-4 w-4" />} title="Due for Retention Review" description="Not tested in the past 7 days" />
              <div className="flex flex-wrap gap-1.5">
                {d.stale_topics.map((t) => (
                  <Badge key={t} tone="gray">{t}</Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* Full Topic Graph */}
      <Card className="mt-6">
        <CardHeader
          showDot
          icon={<BarChart3 className="h-4 w-4" />}
          title="Estimated Topic Mastery Breakdown"
          description="Syllabus topics ordered from lowest to highest score"
        />
        <LearningGraph mastery={d.mastery} />
        <CardTakeaway
          text={
            d.mastery.length > 0
              ? `Review the lowest estimated topics to prepare for upcoming evaluations.`
              : "Complete your initial quizzes to build your progress breakdown."
          }
        />
      </Card>

      {/* Dedicated Personalised Recommendations for Weak Topics */}
      <div className="mt-6">
        <RecommendedLearningSection classId={activeClass.id} />
      </div>
    </PageContainer>
  );
}
