import { AppShell } from "../components/layout/AppShell";

export default function EducatorLayout({ children }: { children: React.ReactNode }) {
  return <AppShell role="educator">{children}</AppShell>;
}
