"use client";

import type { ReactNode } from "react";
import type { ClassRow } from "../../lib/types";
import { useClasses } from "../../lib/hooks/useClasses";
import { useActiveClass } from "../../lib/hooks/useActiveClass";
import { ErrorState, PageSkeleton } from "../ui/Feedback";
import { PageContainer } from "../ui/PageHeader";
import { ClassPicker } from "./ClassPicker";
import { JoinClassPanel } from "./JoinClassPanel";

export function StudentClassGate({
  children,
  width = "default",
}: {
  children: (activeClass: ClassRow, picker: (className?: string) => ReactNode) => ReactNode;
  width?: "narrow" | "default" | "wide";
}) {
  const classes = useClasses();
  const [active, setActive] = useActiveClass(classes.data);

  if (classes.error && !classes.data) {
    return (
      <PageContainer width={width}>
        <ErrorState message={classes.error} onRetry={classes.reload} />
      </PageContainer>
    );
  }
  if (!classes.data) {
    return (
      <PageContainer width={width}>
        <PageSkeleton />
      </PageContainer>
    );
  }
  if (classes.data.length === 0 || !active) return <JoinClassPanel onJoined={classes.reload} />;

  const list = classes.data;
  const picker = (className?: string) => (
    <ClassPicker classes={list} value={active.id} onChange={setActive} className={className} />
  );
  return <>{children(active, picker)}</>;
}
