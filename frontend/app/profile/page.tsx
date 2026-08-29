"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "../lib/api";
import { useAuth, useAuthActions } from "../lib/hooks/useAuth";
import type { ClassRow, DashboardResponse, User } from "../lib/types";
import { Navbar } from "../components/layout/Navbar";
import { StudentSidebar } from "../components/layout/StudentSidebar";
import { EducatorSidebar } from "../components/layout/EducatorSidebar";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";

export default function ProfilePage() {
  const { user: authUser, loading: authLoading } = useAuth();
  const { logout } = useAuthActions();

  const [fullName, setFullName] = useState("");
  const [savingName, setSavingName] = useState(false);
  const [nameMessage, setNameMessage] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const [classes, setClasses] = useState<ClassRow[] | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);

  useEffect(() => {
    if (authUser) setFullName(authUser.full_name);
  }, [authUser]);

  useEffect(() => {
    if (!authUser) return;
    apiFetch<ClassRow[]>("/classes/").then(setClasses);
    if (authUser.role === "student") {
      apiFetch<DashboardResponse>("/progress/dashboard").then(setDashboard).catch(() => {});
    }
  }, [authUser]);

  async function handleSaveName(e: FormEvent) {
    e.preventDefault();
    setSavingName(true);
    setNameMessage(null);
    setNameError(null);
    try {
      await apiFetch<User>("/auth/me", { method: "PATCH", body: { full_name: fullName } });
      setNameMessage("Name updated.");
    } catch (err) {
      setNameError(err instanceof ApiError ? err.message : "Failed to update name.");
    } finally {
      setSavingName(false);
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    setSavingPassword(true);
    setPasswordMessage(null);
    setPasswordError(null);
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: { current_password: currentPassword, new_password: newPassword },
      });
      setPasswordMessage("Password changed.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setPasswordError(err instanceof ApiError ? err.message : "Failed to change password.");
    } finally {
      setSavingPassword(false);
    }
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm text-tertiary">Loading…</p>
      </div>
    );
  }

  if (!authUser) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm text-danger">Could not load profile.</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        {authUser.role === "educator" ? <EducatorSidebar /> : <StudentSidebar />}
        <main className="flex-1 p-6 pb-20 md:pb-6 bg-app">
          <div className="max-w-2xl mx-auto flex flex-col gap-6">
            <h1 className="text-2xl font-bold text-primary">Profile</h1>

            <Card>
              <h2 className="font-semibold text-primary mb-3">Account</h2>
              <div className="flex flex-col gap-3 text-sm mb-4">
                <div className="flex items-center justify-between">
                  <span className="text-secondary">Email</span>
                  <span className="text-primary">{authUser.email}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary">Role</span>
                  <Badge tone={authUser.role === "educator" ? "blue" : "gray"}>{authUser.role}</Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-secondary">Member since</span>
                  <span className="text-primary">{new Date(authUser.created_at).toLocaleDateString()}</span>
                </div>
              </div>

              <form onSubmit={handleSaveName} className="flex flex-col gap-3">
                <Input id="full_name" label="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
                {nameError && <p className="text-sm text-danger">{nameError}</p>}
                {nameMessage && <p className="text-sm text-success">{nameMessage}</p>}
                <Button type="submit" variant="secondary" loading={savingName} className="w-fit">
                  Save name
                </Button>
              </form>
            </Card>

            <Card>
              <h2 className="font-semibold text-primary mb-3">Change password</h2>
              <form onSubmit={handleChangePassword} className="flex flex-col gap-3">
                <Input
                  id="current_password"
                  label="Current password"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <Input
                  id="new_password"
                  label="New password"
                  type="password"
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  required
                />
                {passwordError && <p className="text-sm text-danger">{passwordError}</p>}
                {passwordMessage && <p className="text-sm text-success">{passwordMessage}</p>}
                <Button type="submit" variant="secondary" loading={savingPassword} className="w-fit">
                  Change password
                </Button>
              </form>
            </Card>

            {authUser.role === "student" && dashboard && (
              <Card>
                <h2 className="font-semibold text-primary mb-3">Snapshot</h2>
                <div className="flex items-center gap-6">
                  <div>
                    <div className="text-2xl font-bold text-primary">{dashboard.engagement.current_streak}</div>
                    <div className="text-xs text-tertiary">day streak</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-primary">
                      {dashboard.mastery.length > 0
                        ? Math.round(
                            (dashboard.mastery.reduce((sum, m) => sum + m.score, 0) / dashboard.mastery.length) * 100
                          )
                        : 0}
                      %
                    </div>
                    <div className="text-xs text-tertiary">avg mastery</div>
                  </div>
                  <Link href="/progress" className="text-sm text-accent-secondary hover:underline ml-auto">
                    View full progress
                  </Link>
                </div>
              </Card>
            )}

            <Card>
              <h2 className="font-semibold text-primary mb-3">
                {authUser.role === "educator" ? "Classes you teach" : "Your classes"}
              </h2>
              {classes === null ? (
                <p className="text-sm text-tertiary">Loading…</p>
              ) : classes.length === 0 ? (
                <p className="text-sm text-tertiary">
                  {authUser.role === "educator" ? "You haven't created a class yet." : "You're not enrolled in any class yet."}
                </p>
              ) : (
                <div className="flex flex-col gap-2">
                  {classes.map((c) => (
                    <div key={c.id} className="flex items-center justify-between text-sm border-t border-subtle pt-2 first:border-t-0 first:pt-0">
                      <span className="text-primary">
                        {c.name} {c.subject ? <span className="text-tertiary">— {c.subject}</span> : null}
                      </span>
                      <Link
                        href={authUser.role === "educator" ? `/insights?class_id=${c.id}` : "/chat"}
                        className="text-accent-secondary hover:underline"
                      >
                        {authUser.role === "educator" ? "View insights" : "Go to chat"}
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Button variant="secondary" onClick={logout} className="w-fit">
              Sign out
            </Button>
          </div>
        </main>
      </div>
    </div>
  );
}
