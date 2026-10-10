import { AppShell } from "../components/layout/AppShell";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return <AppShell role="student">{children}</AppShell>;
}
