"use client";

import type { ClassRow } from "../../lib/types";
import { Select } from "../ui/Input";

export function ClassPicker({
  classes,
  value,
  onChange,
  label = "Class",
  className = "w-full sm:w-72",
}: {
  classes: ClassRow[];
  value: string;
  onChange: (id: string) => void;
  label?: string;
  className?: string;
}) {
  if (classes.length <= 1) return null;
  return (
    <Select
      label={label}
      srOnlyLabel
      value={value}
      onChange={(e) => onChange(e.target.value)}
      wrapperClassName={className}
    >
      {classes.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
        </option>
      ))}
    </Select>
  );
}
