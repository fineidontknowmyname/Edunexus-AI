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
  { value: "student", label: "Student", description: "Learn with an AI tutor", icon: GraduationCap },
  { value: "educator", label: "Educator", description: "Teach and track a class", icon: Presentation },
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
      setError(errorMessage(err, "Registration failed. Please try again."));
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight text-primary">Create your account</h1>
      <p className="mt-1.5 text-sm text-tertiary">It takes less than a minute.</p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium text-secondary">I am a…</legend>
          <div className="grid grid-cols-2 gap-2">
            {ROLES.map(({ value, label, description, icon: Icon }) => {
              const selected = role === value;
              return (
                <label
                  key={value}
                  className={cn(
                    "relative flex cursor-pointer flex-col gap-1 rounded-lg border p-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
                    selected ? "border-accent-secondary bg-accent-secondary/8" : "border-strong bg-surface hover:bg-surface-muted"
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
                  <Icon className={cn("h-4 w-4", selected ? "text-accent-secondary" : "text-tertiary")} aria-hidden />
                  <span className="text-sm font-semibold text-primary">{label}</span>
                  <span className="text-xs text-tertiary">{description}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
        <Input
          id="full_name"
          label="Full name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          autoComplete="name"
        />
        <Input
          id="email"
          label="Email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          placeholder="you@school.edu"
        />
        <PasswordInput
          id="password"
          label="Password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          hint="At least 8 characters."
        />

        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" size="lg" loading={loading} className="mt-2 w-full">
          {loading ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-tertiary">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-accent-secondary hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
