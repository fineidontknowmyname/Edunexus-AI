import { Logo } from "../components/layout/Logo";
import { ThemeToggle } from "../components/ui/ThemeToggle";

const HIGHLIGHTS = [
  { num: "01", title: "Grounded in curriculum", text: "Answers cite verified faculty syllabus materials with direct academic evidence." },
  { num: "02", title: "Adaptive learning path", text: "Diagnostics evaluate topic mastery and calibrate your personalised study sequence." },
  { num: "03", title: "Actionable cohort insights", text: "Empowers educators with misconception detection and timely intervention tools." },
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-dvh bg-bg text-ink lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden border-r border-line bg-surface p-12 lg:flex">
        <Logo />
        <div className="relative max-w-md my-auto py-12">
          <span className="font-mono text-xs uppercase tracking-[0.08em] text-accent-red">
            [ SYSTEM ACCESS / WORKSPACE ]
          </span>
          <h2 className="font-serif text-[42px] font-normal leading-[1.05] tracking-tight text-ink mt-3">
            Master your syllabus with targeted AI guidance.
          </h2>
          <ul className="mt-10 flex flex-col gap-6">
            {HIGHLIGHTS.map(({ num, title, text }) => (
              <li key={num} className="flex items-start gap-4">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line bg-surface2 font-mono text-xs font-semibold text-accent-red" aria-hidden="true">
                  {num}
                </span>
                <div>
                  <p className="font-serif text-[17px] text-ink">{title}</p>
                  <p className="mt-0.5 text-xs text-muted leading-relaxed font-sans">{text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
          EduNexus AI · Academic Intelligence Engine
        </p>
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
