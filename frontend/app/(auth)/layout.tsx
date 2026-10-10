import { BarChart3, MessageSquare, Route } from "lucide-react";
import { Logo } from "../components/layout/Logo";
import { ThemeToggle } from "../components/ui/ThemeToggle";

const HIGHLIGHTS = [
  { icon: MessageSquare, title: "A tutor grounded in your curriculum", text: "Answers cite your teacher's materials and flag anything that isn't." },
  { icon: Route, title: "A path that adapts to you", text: "Quizzes update your mastery and reorder what to study next." },
  { icon: BarChart3, title: "Insight for educators", text: "See where the class is struggling before the exam does." },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-app lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-subtle bg-surface p-12 lg:flex">
        <div
          className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-accent-secondary/10 blur-3xl"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-accent-tertiary/10 blur-3xl"
          aria-hidden
        />
        <Logo />
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-primary">
            Learn what matters, in the order that matters.
          </h2>
          <ul className="mt-8 flex flex-col gap-5">
            {HIGHLIGHTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-3.5">
                <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-secondary/12 text-accent-secondary" aria-hidden>
                  <Icon className="h-4 w-4" />
                </span>
                <div>
                  <p className="text-sm font-semibold text-primary">{title}</p>
                  <p className="mt-0.5 text-sm text-tertiary">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-tertiary">Adaptive AI tutoring for classrooms.</p>
      </aside>
      <div className="flex flex-col">
        <div className="flex items-center justify-between p-4 sm:p-6">
          <span className="lg:invisible">
            <Logo />
          </span>
          <ThemeToggle />
        </div>
        <main className="flex flex-1 items-center justify-center px-4 pb-12 sm:px-6">{children}</main>
      </div>
    </div>
  );
}
