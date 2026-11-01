"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ArrowRight, KeyRound, LogOut, Plus, School, Trash2, UserRound, Award } from "lucide-react";
import { apiFetch, errorMessage } from "../lib/api";
import { useAuth, useAuthActions } from "../lib/hooks/useAuth";
import { useApi } from "../lib/hooks/useApi";
import { formatDate, percent } from "../lib/format";
import type { ClassRow, DashboardResponse, User } from "../lib/types";
import { Card, CardHeader, CardTakeaway } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { PasswordInput } from "../components/ui/PasswordInput";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonText } from "../components/ui/Feedback";
import { PageContainer, PageHeader } from "../components/ui/PageHeader";
import { ProgressBar } from "../components/ui/Stat";
import { Avatar } from "../components/layout/UserMenu";
import { ConfirmDialog, Modal } from "../components/ui/Modal";
import { JoinClassPanel } from "../components/layout/JoinClassPanel";
import { ProgressRing } from "../components/ui/DataVisualizations";

function NameForm({ user }: { user: User }) {
  const [fullName, setFullName] = useState(user.full_name);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await apiFetch<User>("/auth/me", { method: "PATCH", body: { full_name: fullName } });
      setMessage("Your name has been updated.");
    } catch (err) {
      setError(errorMessage(err, "Failed to update name."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="flex flex-col gap-3">
      <Input id="full_name" label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required autoComplete="name" />
      {error && <Alert tone="danger">{error}</Alert>}
      {message && <Alert tone="success">{message}</Alert>}
      <Button type="submit" variant="secondary" loading={saving} disabled={fullName.trim() === user.full_name} className="w-fit">
        Save name
      </Button>
    </form>
  );
}

function PasswordForm() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleChange(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: { current_password: currentPassword, new_password: newPassword },
      });
      setMessage("Password changed successfully.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(errorMessage(err, "Failed to change password."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleChange} className="flex flex-col gap-3">
      <PasswordInput
        id="current_password"
        label="Current password"
        value={currentPassword}
        onChange={(e) => setCurrentPassword(e.target.value)}
        autoComplete="current-password"
        required
      />
      <PasswordInput
        id="new_password"
        label="New password"
        minLength={8}
        value={newPassword}
        onChange={(e) => setNewPassword(e.target.value)}
        autoComplete="new-password"
        hint="At least 8 characters."
        required
      />
      {error && <Alert tone="danger">{error}</Alert>}
      {message && <Alert tone="success">{message}</Alert>}
      <Button type="submit" variant="secondary" loading={saving} className="w-fit">
        Change password
      </Button>
    </form>
  );
}

function StudentProgressSummary() {
  const dashboard = useApi<DashboardResponse>("/progress/dashboard");
  if (!dashboard.data) return null;
  const d = dashboard.data;
  const topTopics = [...d.mastery].sort((a, b) => b.score - a.score).slice(0, 4);

  return (
    <Card className="flex flex-col gap-5">
      <CardHeader
        showDot
        icon={<Award className="h-4 w-4" />}
        title="Evaluated Curriculum Topics"
        description="Estimated mastery levels across recently assessed areas"
        linkHref="/progress"
      />
      <div className="space-y-4">
        {topTopics.map((m) => (
          <div key={m.topic} className="rounded-[2px] p-3 bg-surface border border-line">
            <div className="flex items-center justify-between text-xs mb-1.5">
              <span className="font-serif text-[15px] text-ink truncate max-w-[70%]">{m.topic}</span>
              <span className="font-mono text-xs tabular-nums text-ink">Est. {percent(m.score)}</span>
            </div>
            <ProgressBar value={m.score} label={`${m.topic} estimated mastery`} />
          </div>
        ))}
      </div>
      <CardTakeaway text={`${d.mastery.length} topics currently tracked across all enrolled classes.`} />
    </Card>
  );
}

export default function ProfilePage() {
  const { user, loading, error } = useAuth();
  const { logout } = useAuthActions();
  const classes = useApi<ClassRow[]>(user ? "/classes/" : null);
  const dashboard = useApi<DashboardResponse>(user?.role === "student" ? "/progress/dashboard" : null);

  const [joinOpen, setJoinOpen] = useState(false);
  const [leavingClass, setLeavingClass] = useState<ClassRow | null>(null);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [leaveError, setLeaveError] = useState<string | null>(null);

  if (loading) return <PageContainer width="narrow"><PageSkeleton cards={3} /></PageContainer>;
  if (!user) {
    return (
      <PageContainer width="narrow">
        <ErrorState title="Couldn't load your profile" message={error} onRetry={() => window.location.reload()} />
      </PageContainer>
    );
  }

  const isEducator = user.role === "educator";
  const d = dashboard.data;
  const avg = d && d.mastery.length > 0 ? d.mastery.reduce((sum, m) => sum + m.score, 0) / d.mastery.length : null;

  async function handleConfirmLeave() {
    if (!leavingClass) return;
    setLeaveLoading(true);
    setLeaveError(null);
    try {
      await apiFetch(`/classes/${leavingClass.id}/enroll`, { method: "DELETE" });
      if (typeof window !== "undefined") {
        try {
          const active = localStorage.getItem("edunexus_active_class");
          if (active === leavingClass.id) {
            localStorage.removeItem("edunexus_active_class");
            window.dispatchEvent(new Event("edunexus-active-class-change"));
          }
        } catch {}
      }
      setLeavingClass(null);
      classes.reload();
    } catch (err) {
      setLeaveError(errorMessage(err, "Couldn't leave class."));
    } finally {
      setLeaveLoading(false);
    }
  }

  return (
    <PageContainer width="narrow">
      <PageHeader
        eyebrow="[ USER SETTINGS ]"
        title="Scholar Profile"
        description="Account details, enrolled classes, and learning metrics."
      />

      {/* Profile Header Card */}
      <Card className="p-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-4 text-center sm:text-left">
            <Avatar name={user.full_name} className="h-16 w-16 text-xl bg-ink text-bg font-mono" />
            <div className="min-w-0">
              <h2 className="font-serif text-2xl text-ink tracking-tight">{user.full_name}</h2>
              <p className="font-mono text-xs text-muted">{user.email}</p>
              <div className="mt-2 flex flex-wrap items-center justify-center sm:justify-start gap-2">
                <span className="rounded-full border border-line bg-surface2 px-2.5 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-ink">
                  {user.role}
                </span>
                <span className="font-mono text-[11px] text-muted uppercase tracking-[0.04em]">
                  Joined {formatDate(user.created_at)}
                </span>
              </div>
            </div>
          </div>

          {!isEducator && avg !== null && (
            <div className="flex flex-col items-center shrink-0">
              <ProgressRing
                value={avg}
                size={96}
                strokeWidth={7}
                label={<span className="font-serif text-xl text-ink">{percent(avg)}</span>}
                sublabel="Est. Avg"
                color="stroke-accent-red"
              />
            </div>
          )}
        </div>
      </Card>

      {/* Student Progress Topics with Bars */}
      {!isEducator && <StudentProgressSummary />}

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader showDot icon={<UserRound className="h-4 w-4" />} title="Account Info" description="How your name appears in class" />
          <NameForm user={user} />
        </Card>
        <Card>
          <CardHeader showDot icon={<KeyRound className="h-4 w-4" />} title="Security" description="Update your access password" />
          <PasswordForm />
        </Card>
      </div>

      <Card>
        <CardHeader
          showDot
          icon={<School className="h-4 w-4" />}
          title={isEducator ? "Classes You Teach" : "Enrolled Classes"}
          actions={
            !isEducator && classes.data && classes.data.length > 0 ? (
              <Button
                variant="secondary"
                size="sm"
                icon={<Plus className="h-3.5 w-3.5" aria-hidden />}
                onClick={() => setJoinOpen(true)}
              >
                Join class
              </Button>
            ) : undefined
          }
        />
        {leaveError && (
          <Alert tone="danger" className="mb-4" onDismiss={() => setLeaveError(null)}>
            {leaveError}
          </Alert>
        )}
        {classes.error ? (
          <ErrorState message={classes.error} onRetry={classes.reload} />
        ) : !classes.data ? (
          <SkeletonText lines={2} />
        ) : classes.data.length === 0 ? (
          <EmptyState
            compact
            title={isEducator ? "You haven't created a class yet" : "You're not enrolled in a class yet"}
            action={
              isEducator ? (
                <Link href="/upload" className="font-mono text-xs uppercase tracking-[0.06em] text-accent-red hover:underline">
                  Create a class
                </Link>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  icon={<Plus className="h-4 w-4" aria-hidden />}
                  onClick={() => setJoinOpen(true)}
                >
                  Join a class
                </Button>
              )
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            <ul className="flex flex-col divide-y divide-line">
              {classes.data.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="truncate font-serif text-[16px] text-ink">{c.name}</p>
                    <div className="flex flex-wrap items-center gap-2 mt-0.5">
                      {c.subject && <span className="truncate font-mono text-xs text-muted">{c.subject}</span>}
                      {isEducator && c.join_code && (
                        <Badge tone="red" className="font-mono text-[10px]">
                          Join code: {c.join_code}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Link
                      href={isEducator ? `/insights?class_id=${c.id}` : "/chat"}
                      className="inline-flex shrink-0 items-center gap-1 font-mono text-xs uppercase tracking-[0.04em] text-accent-red hover:underline"
                    >
                      {isEducator ? "Insights" : "Open chat"}
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </Link>
                    {!isEducator && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-muted hover:text-danger hover:bg-danger/10"
                        onClick={() => setLeavingClass(c)}
                        aria-label={`Leave ${c.name}`}
                      >
                        <Trash2 className="h-4 w-4" aria-hidden />
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <div className="flex justify-end pt-2">
        <Button
          variant="ghost"
          onClick={logout}
          icon={<LogOut className="h-4 w-4" aria-hidden />}
          className="text-danger hover:bg-danger/10"
        >
          Sign out
        </Button>
      </div>

      <ConfirmDialog
        open={Boolean(leavingClass)}
        onCancel={() => setLeavingClass(null)}
        onConfirm={handleConfirmLeave}
        title="Leave class?"
        description={
          leavingClass
            ? `Are you sure you want to leave ${leavingClass.name}? You will need the join code to re-enroll.`
            : ""
        }
        confirmLabel="Leave class"
        loading={leaveLoading}
        tone="danger"
      />

      <Modal open={joinOpen} onClose={() => setJoinOpen(false)} title="Join a class">
        <JoinClassPanel
          onJoined={() => {
            setJoinOpen(false);
            classes.reload();
          }}
        />
      </Modal>
    </PageContainer>
  );
}
