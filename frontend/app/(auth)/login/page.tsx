"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useAuthActions } from "../../lib/hooks/useAuth";
import { errorMessage } from "../../lib/api";
import { Input } from "../../components/ui/Input";
import { PasswordInput } from "../../components/ui/PasswordInput";
import { Button } from "../../components/ui/Button";
import { Alert } from "../../components/ui/Feedback";

export default function LoginPage() {
  const { login } = useAuthActions();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(errorMessage(err, "Login failed. Please try again."));
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      <h1 className="text-2xl font-semibold tracking-tight text-primary">Welcome back</h1>
      <p className="mt-1.5 text-sm text-tertiary">Sign in to continue to EduNexus AI.</p>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
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
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" size="lg" loading={loading} className="mt-2 w-full">
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-tertiary">
        New to EduNexus?{" "}
        <Link href="/register" className="font-medium text-accent-secondary hover:underline">
          Create an account
        </Link>
      </p>
    </div>
  );
}
