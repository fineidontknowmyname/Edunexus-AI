"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { useAuth, homeForRole } from "./lib/hooks/useAuth";
import { Logo } from "./components/layout/Logo";
import { ButtonLink } from "./components/ui/Button";
import { ThemeToggle } from "./components/ui/ThemeToggle";

export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (!loading && user) {
      router.replace(homeForRole(user.role));
    }
  }, [user, loading, router]);

  if (loading) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center bg-bg p-6 text-ink">
        <div className="flex flex-col items-center gap-4">
          <Logo />
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.1em] text-muted">
            <span className="dot animate-ping" />
            <span>Loading workspace…</span>
          </div>
        </div>
      </main>
    );
  }

  if (user) {
    return null;
  }

  return (
    <main className="min-h-dvh flex flex-col bg-bg text-ink">
      {/* Reference Sticky Topbar */}
      <header className="topbar">
        <div className="top-inner shell">
          <Logo />
          <div className="top-actions">
            <ThemeToggle />
            <ButtonLink href="/login" variant="outline" size="sm">
              Sign in
            </ButtonLink>
            <ButtonLink href="/register" variant="primary" size="sm">
              Get started
            </ButtonLink>
          </div>
        </div>
      </header>

      {/* Reference Hero Split Layout */}
      <section className="hero shell flex-1">
        <div className="hero-main">
          <div>
            <div className="eyebrow mono mb-6">
              <i className="dot" aria-hidden /> ADAPTIVE HIGHER EDUCATION PLATFORM{" "}
              <span className="muted">/ 2026—27</span>
            </div>

            <h1 className="kinetic text-ink leading-[0.91]">
              Master your syllabus with{" "}
              <br />
              <em className="text-red font-normal">curriculum-aware AI</em>.
            </h1>
          </div>

          <div className="hero-bottom mt-8">
            <p>
              EduNexus grounds every diagnostic quiz, personalized recommendation, and tutor response in your institution&apos;s verified curriculum materials. One clear path from concept to mastery.
            </p>

            <div className="min-w-[200px]">
              <div className="mono muted mb-2">CURRICULUM ALIGNMENT</div>
              <div className="font-serif text-3xl leading-none">
                100<small className="mono muted text-[10px] ml-1">% VERIFIED</small>
              </div>
              <div className="progress-line mt-2">
                <span style={{ width: "100%" }} />
              </div>
              <div className="mt-4 flex items-center gap-2">
                <ButtonLink href="/login" variant="primary" size="sm" icon={<ArrowRight className="h-3 w-3" />}>
                  Enter Workspace
                </ButtonLink>
                <ButtonLink href="/register" variant="outline" size="sm">
                  Register
                </ButtonLink>
              </div>
            </div>
          </div>
        </div>

        {/* Hero Right Aside with Animated Orbit Feature Cover */}
        <aside className="hero-aside">
          <div className="aside-top mono muted">
            <span>[ SYSTEM CORE ]</span>
            <span className="red">● REAL-TIME GROUNDING</span>
          </div>

          <div className="feature-cover my-6">
            <div className="cover-art">
              <i className="orbit" aria-hidden />
              <i className="orbit" aria-hidden />
              <i className="orbit" aria-hidden />
            </div>
            <div className="cover-meta font-mono text-[9px] uppercase tracking-wider text-muted mt-4">
              <span>MODULE 01 / GROUNDED ARCHITECTURE</span>
              <span>INSTITUTIONAL AI</span>
            </div>
            <h2 className="font-serif text-3xl text-panel-dark-text my-2 leading-none">
              Zero hallucination, pure syllabus.
            </h2>
            <p className="font-sans text-xs text-muted max-w-[280px] leading-relaxed">
              Every question, quiz, and Socratic hint links directly to faculty slide decks and chapters.
            </p>
            <div className="cover-foot font-mono text-[9px] uppercase tracking-wider border-t border-line/30 pt-3 mt-4 flex justify-between text-muted">
              <span>FACULTY CURATED</span>
              <span>VERIFIED SOURCES ↗</span>
            </div>
          </div>

          <div className="aside-stats mono text-[10px] flex justify-between border-t border-line pt-4 text-muted">
            <span>ALIGNMENT <b className="red font-normal">STRICT</b></span>
            <span>MODEL <b className="font-normal text-ink">CURRICULUM RAG</b></span>
          </div>
        </aside>
      </section>

      {/* Reference Section Header */}
      <section className="shell border-b border-line">
        <div className="section-head">
          <div>
            <div className="mono red">[ 01 — CORE CAPABILITIES ]</div>
            <h2 className="font-serif text-3xl sm:text-4xl text-ink leading-tight mt-1">
              Deliberately designed for higher education
            </h2>
          </div>
          <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted max-w-xs text-right hidden sm:block">
            STRUCTURED LEARNING · MEASURABLE PROGRESS
          </p>
        </div>

        {/* Reference Hairline 3-Column Feature Cards */}
        <div className="course-grid">
          {/* Pillar 1: Grounded AI Tutor */}
          <article className="course-card">
            <div>
              <div className="course-meta">
                <span>PILLAR 01 / TUTOR</span>
                <span>SOCRATIC GUIDANCE</span>
              </div>
              <div className="book">
                <div className="mono text-muted mb-1">EVIDENCE-BASED</div>
                <h3 className="font-serif text-2xl text-ink leading-tight">Grounded AI Tutor</h3>
                <p className="font-sans text-xs text-muted mt-2 leading-relaxed">
                  Step-by-step Socratic assistance citing actual faculty documents and textbook chapters.
                </p>
              </div>
            </div>
            <div>
              <div className="card-foot">
                <span>SOCRATIC METHOD</span>
                <span className="text-red">VERIFIED CITATIONS ↗</span>
              </div>
              <div className="progress-line">
                <span style={{ width: "95%" }} />
              </div>
            </div>
          </article>

          {/* Pillar 2: Adaptive Paths */}
          <article className="course-card">
            <div>
              <div className="course-meta">
                <span>PILLAR 02 / ADAPTIVE</span>
                <span>MASTERY CALIBRATION</span>
              </div>
              <div className="book">
                <div className="mono text-muted mb-1">DIAGNOSTIC</div>
                <h3 className="font-serif text-2xl text-ink leading-tight">Adaptive Learning Paths</h3>
                <p className="font-sans text-xs text-muted mt-2 leading-relaxed">
                  Diagnostic quizzes calibrate topic mastery and prioritize what concepts to review next.
                </p>
              </div>
            </div>
            <div>
              <div className="card-foot">
                <span>EXAM READINESS</span>
                <span className="text-red">MEASURABLE ↗</span>
              </div>
              <div className="progress-line">
                <span style={{ width: "88%" }} />
              </div>
            </div>
          </article>

          {/* Pillar 3: Faculty Telemetry */}
          <article className="course-card">
            <div>
              <div className="course-meta">
                <span>PILLAR 03 / FACULTY</span>
                <span>COHORT INTELLIGENCE</span>
              </div>
              <div className="book">
                <div className="mono text-muted mb-1">SIGNALS &amp; INTERVENTIONS</div>
                <h3 className="font-serif text-2xl text-ink leading-tight">Faculty Telemetry</h3>
                <p className="font-sans text-xs text-muted mt-2 leading-relaxed">
                  Real-time cohort insights, question review queues, and at-risk student monitoring.
                </p>
              </div>
            </div>
            <div>
              <div className="card-foot">
                <span>BETTER SIGNALS</span>
                <span className="text-red">INSTANT OVERSIGHT ↗</span>
              </div>
              <div className="progress-line">
                <span style={{ width: "92%" }} />
              </div>
            </div>
          </article>
        </div>
      </section>

      {/* Reference Footer Strip */}
      <footer className="quiet-footer shell mt-8">
        <span>EDUNEXUS AI / HIGHER EDUCATION LEARNING SYSTEM</span>
        <span>DESIGNED FOR FOCUS · 2026—27</span>
        <span>CURRICULUM INTEGRITY FIRST</span>
      </footer>
    </main>
  );
}
