"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { GraduationCap, Presentation } from "lucide-react";
import { useAuthActions } from "../../lib/hooks/useAuth";
import { errorMessage } from "../../lib/api";
import type { UserRole } from "../../lib/types";
import { Input } from "../../components/ui/Input";
import { PasswordInput } from "../../components/ui/PasswordInput";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Feedback";
import { cn } from "../../lib/cn";

const ROLES: { value: UserRole; label: string; description: string; icon: typeof GraduationCap }[] = [
  { value: "student", label: "Student", description: "Learn with adaptive AI tutor", icon: GraduationCap },
  { value: "educator", label: "Educator", description: "Manage syllabus & cohort", icon: Presentation },
];

export default function RegisterPage() {
  const { register } = useAuthActions();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("student");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register(email, password, fullName, role);
    } catch (err) {
      setError(errorMessage(err, "Registration failed. Please check your details and try again."));
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-[2px] border border-line bg-surface p-8 sm:p-10 shadow-[0_18px_48px_rgba(20,18,15,.08)]">
      <div className="mb-6">
        <span className="font-mono text-xs uppercase tracking-[0.08em] text-accent-red">
          [ 02 / REGISTRATION ]
        </span>
        <h1 className="font-serif text-3xl font-normal text-ink tracking-tight mt-1">
          Create Your Account
        </h1>
        <p className="mt-1 text-xs text-muted font-sans">
          Join EduNexus to access curriculum-grounded learning.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <fieldset>
          <legend className="mb-2 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Select Your Role</legend>
          <div className="grid grid-cols-2 gap-2.5">
            {ROLES.map(({ value, label, description, icon: Icon }) => {
              const selected = role === value;
              return (
                <label
                  key={value}
                  className={cn(
                    "relative flex cursor-pointer flex-col gap-1.5 rounded-[2px] border p-3.5 transition-all duration-150",
                    selected
                      ? "border-ink bg-surface2 text-ink shadow-xs"
                      : "border-line bg-surface hover:border-ink/60"
                  )}
                >
                  <input
                    type="radio"
                    name="role"
                    value={value}
                    checked={selected}
                    onChange={() => setRole(value)}
                    className="sr-only"
                  />
                  <Icon className={cn("h-4 w-4", selected ? "text-accent-red" : "text-muted")} aria-hidden />
                  <span className="font-serif text-[16px] text-ink">{label}</span>
                  <span className="text-[11px] text-muted leading-tight">{description}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <Input
          id="full_name"
          label="Full Name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          autoComplete="name"
          placeholder="Alex Johnson"
        />
        <Input
          id="email"
          label="Email Address"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          placeholder="alex@university.edu"
        />
        <PasswordInput
          id="password"
          label="Password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          hint="Minimum 8 characters."
        />
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" size="lg" variant="primary" loading={loading} className="mt-2 w-full">
          {loading ? "Creating account…" : "Complete Registration"}
        </Button>
      </form>

      <div className="mt-6 pt-5 border-t border-line text-center text-xs text-muted">
        Already registered?{" "}
        <Link href="/login" className="font-mono text-xs uppercase tracking-[0.06em] text-accent-red hover:underline">
          Sign in
        </Link>
      </div>
    </div>
  );
}
