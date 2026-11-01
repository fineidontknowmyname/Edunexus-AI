import {
  BarChart3,
  BookOpen,
  ClipboardCheck,
  FileUp,
  Home,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  Route,
  TrendingUp,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import type { UserRole } from "../../lib/types";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  match?: string[];
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const STUDENT_SECTIONS: NavSection[] = [
  {
    title: "Learning",
    items: [
      { href: "/home", label: "Home", icon: Home },
      { href: "/quiz", label: "Quizzes", icon: ListChecks },
      { href: "/path", label: "Learning path", icon: Route },
      { href: "/progress", label: "Progress", icon: TrendingUp },
    ],
  },
  {
    title: "Study tools",
    items: [
      { href: "/chat", label: "Tutor chat", icon: MessageSquare },
      { href: "/profile", label: "Profile & Settings", icon: UserRound },
    ],
  },
];

export const EDUCATOR_SECTIONS: NavSection[] = [
  {
    title: "Teaching",
    items: [
      { href: "/overview", label: "Overview", icon: LayoutDashboard },
      { href: "/insights", label: "Class insights", icon: BarChart3, match: ["/students"] },
      { href: "/quiz-review", label: "Quiz review", icon: ClipboardCheck },
    ],
  },
  {
    title: "Curriculum",
    items: [
      { href: "/upload", label: "Curriculum upload", icon: FileUp },
      { href: "/subjects", label: "Subjects", icon: BookOpen },
      { href: "/profile", label: "Profile & Settings", icon: UserRound },
    ],
  },
];

export const EDUCATOR_NAV: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/insights", label: "Class insights", icon: BarChart3, match: ["/students"] },
  { href: "/quiz-review", label: "Quiz review", icon: ClipboardCheck },
  { href: "/upload", label: "Curriculum upload", icon: FileUp },
  { href: "/subjects", label: "Subjects", icon: BookOpen },
];

export const STUDENT_NAV: NavItem[] = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/chat", label: "Tutor chat", icon: MessageSquare },
  { href: "/quiz", label: "Quizzes", icon: ListChecks },
  { href: "/path", label: "Learning path", icon: Route },
  { href: "/progress", label: "Progress", icon: TrendingUp },
];

export function sectionsFor(role: UserRole | null | undefined): NavSection[] {
  return role === "educator" ? EDUCATOR_SECTIONS : STUDENT_SECTIONS;
}

export function navFor(role: UserRole | null | undefined): NavItem[] {
  return role === "educator" ? EDUCATOR_NAV : STUDENT_NAV;
}

function matches(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function isActive(pathname: string, item: NavItem): boolean {
  return matches(pathname, item.href) || (item.match ?? []).some((p) => matches(pathname, p));
}
