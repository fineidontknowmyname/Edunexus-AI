"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useAuthActions } from "../../lib/hooks/useAuth";
import { ApiError } from "../../lib/api";
import type { UserRole } from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";

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
      setError(err instanceof ApiError ? err.message : "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-app p-6">
      <Card className="w-full max-w-sm">
        <h1 className="text-2xl font-bold text-primary mb-1">Create an account</h1>
        <p className="text-sm text-tertiary mb-6">Join EduNexus AI</p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
          />
          <Input
            id="password"
            label="Password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />

          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium text-secondary">I am a...</span>
            <div className="flex gap-4">
              {(["student", "educator"] as UserRole[]).map((r) => (
                <label key={r} className="flex items-center gap-2 text-sm text-secondary">
                  <input
                    type="radio"
                    name="role"
                    value={r}
                    checked={role === r}
                    onChange={() => setRole(r)}
                  />
                  {r === "student" ? "Student" : "Educator"}
                </label>
              ))}
            </div>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}
          <Button type="submit" loading={loading} className="w-full">
            Create account
          </Button>
        </form>

        <p className="text-sm text-tertiary mt-4 text-center">
          Already have an account?{" "}
          <Link href="/login" className="text-accent-secondary hover:underline">
            Sign in
          </Link>
        </p>
      </Card>
    </main>
  );
}
