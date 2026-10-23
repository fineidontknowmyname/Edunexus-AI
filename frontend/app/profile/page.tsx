"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ArrowRight, KeyRound, LogOut, Plus, School, Trash2, UserRound } from "lucide-react";
import { apiFetch, errorMessage } from "../lib/api";
import { useAuth, useAuthActions } from "../lib/hooks/useAuth";
import { useApi } from "../lib/hooks/useApi";
import { formatDate, percent } from "../lib/format";
import type { ClassRow, DashboardResponse, User } from "../lib/types";
import { Card, CardHeader } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { PasswordInput } from "../components/ui/PasswordInput";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonText } from "../components/ui/Feedback";
import { PageContainer, PageHeader } from "../components/ui/PageHeader";
import { StatCard } from "../components/ui/Stat";
import { Avatar } from "../components/layout/UserMenu";
import { ConfirmDialog, Modal } from "../components/ui/Modal";
import { JoinClassPanel } from "../components/layout/JoinClassPanel";

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
      setMessage("Password changed.");
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

function StudentSnapshot() {
  const dashboard = useApi<DashboardResponse>("/progress/dashboard");
  if (!dashboard.data) return null;
  const d = dashboard.data;
  const avg = d.mastery.length > 0 ? d.mastery.reduce((sum, m) => sum + m.score, 0) / d.mastery.length : 0;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <StatCard label="Day streak" value={d.engagement.current_streak} hint={`Best: ${d.engagement.longest_streak}`} />
      <StatCard label="Avg mastery" value={percent(avg)} hint={`${d.mastery.length} topics tracked`} />
      <StatCard label="Progress" value={<span className="inline-flex items-center gap-1 text-base">View <ArrowRight className="h-4 w-4" aria-hidden /></span>} href="/progress" />
    </div>
  );
}

export default function ProfilePage() {
  const { user, loading, error } = useAuth();
  const { logout } = useAuthActions();
  const classes = useApi<ClassRow[]>(user ? "/classes/" : null);

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
      <PageHeader title="Profile" description="Manage your account details and password." />

      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <Avatar name={user.full_name} className="h-14 w-14 text-lg" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-lg font-semibold text-primary">{user.full_name}</p>
            <p className="truncate text-sm text-tertiary">{user.email}</p>
          </div>
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <Badge tone={isEducator ? "blue" : "gray"} className="capitalize">{user.role}</Badge>
            <span className="text-xs text-tertiary">Member since {formatDate(user.created_at)}</span>
          </div>
        </div>
      </Card>

      {user.role === "student" && <StudentSnapshot />}

      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <CardHeader icon={<UserRound className="h-4 w-4" />} title="Account" description="How your name appears to teachers." />
          <NameForm user={user} />
        </Card>
        <Card>
          <CardHeader icon={<KeyRound className="h-4 w-4" />} title="Password" description="Use a password you don't use elsewhere." />
          <PasswordForm />
        </Card>
      </div>

      <Card>
        <CardHeader
          icon={<School className="h-4 w-4" />}
          title={isEducator ? "Classes you teach" : "Your classes"}
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
                <Link href="/upload" className="text-sm font-medium text-accent-secondary hover:underline">
                  Create a class
                </Link>
              ) : (
                <Button
                  variant="secondary"
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
            <ul className="flex flex-col divide-y divide-subtle">
              {classes.data.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-primary">{c.name}</p>
                    <div className="flex flex-wrap items-center gap-2">
                      {c.subject && <span className="truncate text-xs text-tertiary">{c.subject}</span>}
                      {isEducator && c.join_code && (
                        <Badge tone="blue" className="font-mono text-[0.6875rem]">
                          Join code: {c.join_code}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Link
                      href={isEducator ? `/insights?class_id=${c.id}` : "/chat"}
                      className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-accent-secondary hover:underline"
                    >
                      {isEducator ? "Insights" : "Open chat"}
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </Link>
                    {!isEducator && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-tertiary hover:text-danger hover:bg-danger/10"
                        onClick={() => setLeavingClass(c)}
                        aria-label={`Leave ${c.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden />
                        <span className="hidden sm:inline">Leave</span>
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      <div>
        <Button variant="secondary" onClick={logout} icon={<LogOut className="h-4 w-4" aria-hidden />}>
          Sign out
        </Button>
      </div>

      <Modal
        open={joinOpen}
        onClose={() => setJoinOpen(false)}
        title="Join a class"
        description="Select a class and enter the join code provided by your teacher."
      >
        <JoinClassPanel
          compact
          onJoined={() => {
            classes.reload();
            setJoinOpen(false);
          }}
        />
      </Modal>

      <ConfirmDialog
        open={leavingClass !== null}
        title="Leave class?"
        description={
          leavingClass
            ? `Are you sure you want to leave "${leavingClass.name}"? Your quizzes, progress and chat history will be kept, and you can re-enroll anytime with the teacher's code.`
            : undefined
        }
        confirmLabel="Leave class"
        tone="danger"
        loading={leaveLoading}
        onConfirm={handleConfirmLeave}
        onCancel={() => {
          if (!leaveLoading) setLeavingClass(null);
        }}
      />
    </PageContainer>
  );
}
