"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/chat", label: "Chat" },
  { href: "/quiz", label: "Quizzes" },
  { href: "/path", label: "Learning Path" },
  { href: "/progress", label: "Progress" },
];

export function StudentSidebar() {
  const pathname = usePathname();

  return (
    <nav className="w-48 border-r border-gray-200 bg-white p-4 flex flex-col gap-1">
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
  );
}
