"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ClassRow } from "../types";
import { useApi } from "./useApi";

export function useClasses() {
  return useApi<ClassRow[]>("/classes/");
}

export function useClassParam(classes: ClassRow[] | null): [string, (id: string) => void] {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requested = searchParams.get("class_id");

  const valid = classes?.some((c) => c.id === requested) ? (requested as string) : classes?.[0]?.id ?? "";

  const setClassId = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("class_id", id);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return [valid, setClassId];
}

