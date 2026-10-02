// src/components/ui/toast.tsx
// The toast queue (Shell · Toasts, Foundations · Feedback):
//   • ToastProvider — context owning the queue and its timers (mount once, high in the tree)
//   • useToast()    — { toast: { error, success, info }, dismiss } for call sites
//   • the stack itself lives in toast-card.tsx
//
// The rules the stack keeps (Shell-Behaviour):
//   • success and info leave after 5s; a toast carrying Undo stays 8s, so the
//     undo is reachable. Hovering or focusing a card pauses its clock.
//   • an error stays 8s (hover or focus holds it) — longer, so it can be read
//     and its Details opened — and always offers a next step: the caller's action (Retry, View log) or a Details toggle that
//     shows the whole message and any `details` text.
//   • newest at the bottom, at most three shown; older ones fold into a
//     "N more" chip that unfolds them.
//
// `toast.x(message)` is the whole API for most call sites; the optional second
// argument adds the one action a toast may carry. Each call returns the
// toast's id so a caller can `dismiss` it early.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";

import { Toaster } from "./toast-card";

export type ToastVariant = "error" | "success" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastOptions {
  /** The one action beside the message ("Open", "View log"). Clicking it also
   *  dismisses the toast. */
  action?: ToastAction;
  /** Shorthand for an Undo action; keeps the toast on screen 8s instead of 5s. */
  undo?: () => void;
  /** Shorthand for a Retry action (meant for errors). */
  retry?: () => void;
  /** Longer text revealed by the card's Details toggle (the daemon's message,
   *  a log line). */
  details?: string;
}

export interface ToastItem {
  id: number;
  variant: ToastVariant;
  message: string;
  action?: ToastAction;
  details?: string;
  /** Milliseconds on screen; `null` stays until dismissed. */
  duration: number | null;
}

type Show = (message: string, options?: ToastOptions) => number;

interface ToastApi {
  error: Show;
  success: Show;
  info: Show;
}

interface ToastContextValue {
  toast: ToastApi;
  dismiss: (id: number) => void;
}

export const TOAST_DURATION_MS = 5000;
export const UNDO_TOAST_DURATION_MS = 8000;
export const ERROR_TOAST_DURATION_MS = 8000;

const ToastContext = createContext<ToastContextValue | null>(null);

interface Clock {
  timer?: ReturnType<typeof setTimeout>;
  remaining: number;
  startedAt: number;
}

function toItem(
  id: number,
  variant: ToastVariant,
  message: string,
  o: ToastOptions,
  t: (k: string) => string,
): ToastItem {
  const action =
    o.action ??
    (o.undo ? { label: t("common.undo"), onClick: o.undo } : undefined) ??
    (o.retry ? { label: t("common.retry"), onClick: o.retry } : undefined);
  const duration =
    variant === "error"
      ? ERROR_TOAST_DURATION_MS
      : o.undo
        ? UNDO_TOAST_DURATION_MS
        : TOAST_DURATION_MS;
  return { id, variant, message, action, details: o.details, duration };
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);
  const clocks = useRef(new Map<number, Clock>());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((tn) => tn.id !== id));
    const clock = clocks.current.get(id);
    if (clock?.timer) clearTimeout(clock.timer);
    clocks.current.delete(id);
  }, []);

  const run = useCallback(
    (id: number) => {
      const clock = clocks.current.get(id);
      if (!clock || clock.timer) return;
      clock.startedAt = Date.now();
      clock.timer = setTimeout(() => dismiss(id), clock.remaining);
    },
    [dismiss],
  );

  const pause = useCallback((id: number) => {
    const clock = clocks.current.get(id);
    if (!clock?.timer) return;
    clearTimeout(clock.timer);
    clock.timer = undefined;
    clock.remaining = Math.max(0, clock.remaining - (Date.now() - clock.startedAt));
  }, []);

  const push = useCallback(
    (variant: ToastVariant, message: string, options: ToastOptions = {}) => {
      const id = nextId.current++;
      const item = toItem(id, variant, message, options, t);
      setToasts((prev) => [...prev, item]);
      if (item.duration !== null) {
        clocks.current.set(id, { remaining: item.duration, startedAt: Date.now() });
        run(id);
      }
      return id;
    },
    [run, t],
  );

  // Snapshot the map for cleanup so the lint rule that flags a possibly
  // changed ref at cleanup time is satisfied.
  useEffect(() => {
    const pending = clocks.current;
    return () => pending.forEach((c) => c.timer && clearTimeout(c.timer));
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      toast: {
        error: (m, o) => push("error", m, o),
        success: (m, o) => push("success", m, o),
        info: (m, o) => push("info", m, o),
      },
      dismiss,
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} onPause={pause} onResume={run} />
    </ToastContext.Provider>
  );
}

// No-op fallback used when no ToastProvider is mounted (e.g. isolated unit
// tests that render a single mutation-driven component). This keeps `useToast`
// callable everywhere without forcing every test to wrap in a provider; real
// app code always has the provider mounted in App.tsx.
const NOOP_TOAST: ToastContextValue = {
  toast: { error: () => -1, success: () => -1, info: () => -1 },
  dismiss: () => {},
};

export function useToast(): ToastContextValue {
  return useContext(ToastContext) ?? NOOP_TOAST;
}
