import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AppShell } from "../components/layout/AppShell";
import type { UserRole } from "../lib/types";

export const metadata: Metadata = { title: "Profile · EduNexus AI" };

export default async function ProfileLayout({ children }: { children: React.ReactNode }) {
  const role = (await cookies()).get("edunexus_role")?.value;
  const resolved: UserRole | null = role === "educator" || role === "student" || role === "admin" ? role : null;
  return <AppShell role={resolved}>{children}</AppShell>;
}
