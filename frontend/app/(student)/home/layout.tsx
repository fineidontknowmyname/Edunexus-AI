import type { Metadata } from "next";

export const metadata: Metadata = { title: "Home · EduNexus AI" };

export default function HomeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
