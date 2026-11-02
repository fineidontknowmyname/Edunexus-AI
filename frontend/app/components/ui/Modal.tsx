"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "../../lib/cn";
import { Button } from "./Button";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

let scrollLockCount = 0;
let scrollLockSnapshot: {
  bodyOverflow: string;
  bodyPaddingRight: string;
  htmlOverflow: string;
} | null = null;

function lockDocumentScroll() {
  if (scrollLockCount === 0) {
    const body = document.body;
    const html = document.documentElement;
    const scrollbarWidth = window.innerWidth - html.clientWidth;
    const bodyPaddingRight = Number.parseFloat(getComputedStyle(body).paddingRight) || 0;
    scrollLockSnapshot = {
      bodyOverflow: body.style.overflow,
      bodyPaddingRight: body.style.paddingRight,
      htmlOverflow: html.style.overflow,
    };
    html.style.overflow = "hidden";
    body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      body.style.paddingRight = `${bodyPaddingRight + scrollbarWidth}px`;
    }
  }
  scrollLockCount += 1;

  return () => {
    scrollLockCount = Math.max(0, scrollLockCount - 1);
    if (scrollLockCount !== 0 || !scrollLockSnapshot) return;
    document.body.style.overflow = scrollLockSnapshot.bodyOverflow;
    document.body.style.paddingRight = scrollLockSnapshot.bodyPaddingRight;
    document.documentElement.style.overflow = scrollLockSnapshot.htmlOverflow;
    scrollLockSnapshot = null;
  };
}

function useOverlay(open: boolean, onClose: () => void, panelRef: React.RefObject<HTMLDivElement | null>) {
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE);
    (focusables && focusables.length > 0 ? focusables[0] : panel)?.focus();

    const releaseScrollLock = lockDocumentScroll();

    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const items = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("keydown", handleKey);
      releaseScrollLock();
      previouslyFocused?.focus?.();
    };
  }, [open, panelRef]);
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  bracket = "MODAL",
  scrollable = false,
  bodyTabIndex,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  bracket?: string;
  scrollable?: boolean;
  bodyTabIndex?: 0;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [portalReady, setPortalReady] = useState(false);
  useEffect(() => {
    const frameId = requestAnimationFrame(() => setPortalReady(true));
    return () => cancelAnimationFrame(frameId);
  }, []);
  useOverlay(open && portalReady, onClose, panelRef);
  if (!open || !portalReady) return null;

  return createPortal(
    <div
      className="modal-overlay"
    >
      <div
        className="fixed inset-0 bg-overlay backdrop-blur-[5px] transition-opacity duration-400"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          "relative z-10 w-full rounded-[3px] border border-line bg-surface shadow-shadow animate-[pageIn_0.35s_cubic-bezier(0.16,1,0.3,1)_both]",
          scrollable
            ? "modal-panel-scrollable flex max-w-[640px] flex-col overflow-hidden p-0"
            : "mx-auto max-w-lg p-6 sm:p-7"
        )}
      >
        <header className={cn(scrollable && "shrink-0 px-5 pt-5 sm:px-7 sm:pt-7")}>
          <div className="flex items-start justify-between gap-3">
            <div>
              {bracket && (
                <div className="font-mono text-[9px] uppercase tracking-[0.1em] text-red mb-1">
                  [ {bracket} ]
                </div>
              )}
              <h2
                id={titleId}
                className={cn(
                  "font-serif text-2xl sm:text-[1.75rem] text-ink leading-snug",
                  scrollable && "text-xl sm:text-2xl"
                )}
              >
                {title}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close modal"
              className="h-8 w-8 shrink-0 rounded-full border border-line flex items-center justify-center text-muted hover:border-red hover:text-red hover:rotate-12 transition-all duration-300"
            >
              <X className="h-3.5 w-3.5" aria-hidden />
            </button>
          </div>
          {description && (
            <p className={cn("mt-2 font-sans text-xs sm:text-sm text-muted leading-relaxed", scrollable && "pb-4")}>
              {description}
            </p>
          )}
        </header>
        {children && (
          scrollable ? (
            <div
              className="modal-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5 sm:px-7"
              tabIndex={bodyTabIndex}
            >
              {children}
            </div>
          ) : (
            <div className="mt-5">{children}</div>
          )
        )}
        {footer && (
          scrollable ? (
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-line bg-surface px-5 py-3 sm:px-7">
              {footer}
            </div>
          ) : (
            <div className="mt-6 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end border-t border-line pt-4">
              {footer}
            </div>
          )
        )}
      </div>
    </div>,
    document.body
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  tone = "danger",
  loading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  tone?: "danger" | "primary";
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      description={description}
      bracket="CONFIRMATION"
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={loading}>
            Cancel
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}

export function Drawer({
  open,
  onClose,
  title,
  side = "right",
  children,
  category,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  side?: "left" | "right";
  children: ReactNode;
  category?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useOverlay(open, onClose, panelRef);
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50">
      <div
        className="fixed inset-0 bg-overlay backdrop-blur-[5px] transition-opacity duration-400"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          "fixed inset-y-0 z-51 flex w-[min(850px,100%)] flex-col bg-bg shadow-shadow transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]",
          side === "left" ? "left-0 border-r border-line" : "right-0 border-l border-line"
        )}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-line px-6">
          <div className="flex items-center gap-2">
            {category && (
              <span className="font-mono text-[9px] uppercase tracking-[0.1em] text-red">
                [{category}]
              </span>
            )}
            <h2 id={titleId} className="font-serif text-xl sm:text-2xl text-ink">
              {title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="h-8 w-8 rounded-full border border-line flex items-center justify-center text-muted hover:border-red hover:text-red hover:rotate-12 transition-all duration-300"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
