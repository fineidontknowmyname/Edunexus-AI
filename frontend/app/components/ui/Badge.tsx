import { ReactNode } from "react";

type BadgeTone = "gray" | "blue" | "green" | "red" | "amber";

const TONE_CLASSES: Record<BadgeTone, string> = {
  gray: "bg-gray-100 text-gray-700",
  blue: "bg-blue-100 text-blue-700",
  green: "bg-green-100 text-green-700",
  red: "bg-red-100 text-red-700",
  amber: "bg-amber-100 text-amber-700",
};

export function Badge({ children, tone = "gray" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}
