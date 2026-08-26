"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/upload", label: "Upload" },
  { href: "/quiz-review", label: "Quiz Review" },
  { href: "/insights", label: "Class Insights" },
];

export function EducatorSidebar() {
  const pathname = usePathname();

  return (
    <>
      <nav className="hidden md:flex w-48 border-r border-gray-200 bg-white p-4 flex-col gap-1">
        {LINKS.map((link) => {
          const active = pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`px-3 py-2 rounded-md text-sm font-medium ${
                active ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-20 bg-white border-t border-gray-200 flex justify-around py-2">
        {LINKS.map((link) => {
          const active = pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`px-3 py-1.5 rounded-md text-xs font-medium ${
                active ? "text-blue-700" : "text-gray-600"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
