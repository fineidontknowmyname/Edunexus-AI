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
      setError(errorMessage(err, "Login failed. Please verify your credentials and try again."));
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-[2px] border border-line bg-surface p-8 sm:p-10 shadow-[0_18px_48px_rgba(20,18,15,.08)]">
      <div className="mb-6">
        <span className="font-mono text-xs uppercase tracking-[0.08em] text-accent-red">
          [ 01 / SIGN IN ]
        </span>
        <h1 className="font-serif text-3xl font-normal text-ink tracking-tight mt-1">
          Sign in to EduNexus
        </h1>
        <p className="mt-1 text-xs text-muted font-sans">
          Enter your institutional credentials to access your workspace.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          id="email"
          label="Email Address"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          placeholder="scholar@university.edu"
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
        <Button type="submit" size="lg" variant="primary" loading={loading} className="mt-2 w-full">
          {loading ? "Signing in…" : "Sign In to Workspace"}
        </Button>
      </form>

      <div className="mt-6 pt-5 border-t border-line text-center text-xs text-muted">
        New to EduNexus AI?{" "}
        <Link href="/register" className="font-mono text-xs uppercase tracking-[0.06em] text-accent-red hover:underline">
          Create an account
        </Link>
      </div>
    </div>
  );
}
