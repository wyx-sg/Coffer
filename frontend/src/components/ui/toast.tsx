// src/components/ui/toast.tsx
// A minimal, dependency-free toast/notification system. There was no toast or
// notification surface before, so failed mutations (delete / enable-disable /
// bulk / install) reverted or got stuck silently. This provides:
//   • ToastProvider — context owning the toast queue (mount once, high in the tree)
//   • useToast()    — { toast: { error, success, info }, dismiss } for call sites
//   • Toaster       — the fixed-position stack of toast cards (rendered by the provider)
// Toasts auto-dismiss after a timeout (errors linger longer) and are dismissible
// by hand. Each card is role="alert"/"status" so failures are announced.
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
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

type ToastVariant = "error" | "success" | "info";

interface ToastItem {
  id: number;
  variant: ToastVariant;
  message: string;
}

interface ToastApi {
  error: (message: string) => void;
  success: (message: string) => void;
  info: (message: string) => void;
}

interface ToastContextValue {
  toast: ToastApi;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

// Errors linger so the user can read the failure; transient confirmations clear faster.
const AUTO_DISMISS_MS: Record<ToastVariant, number> = {
  error: 8000,
  success: 4000,
  info: 5000,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((tn) => tn.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (variant: ToastVariant, message: string) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, variant, message }]);
      const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS[variant]);
      timers.current.set(id, timer);
    },
    [dismiss],
  );

  // Snapshot the timers map for cleanup so the lint rule that flags a possibly
  // changed ref at cleanup time is satisfied.
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => clearTimeout(t));
  }, []);

  const value = useMemo<ToastContextValue>(
    () => ({
      toast: {
        error: (m) => push("error", m),
        success: (m) => push("success", m),
        info: (m) => push("info", m),
      },
      dismiss,
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

// No-op fallback used when no ToastProvider is mounted (e.g. isolated unit
// tests that render a single mutation-driven component). This keeps `useToast`
// callable everywhere without forcing every test to wrap in a provider; real
// app code always has the provider mounted in App.tsx.
const NOOP_TOAST: ToastContextValue = {
  toast: { error: () => {}, success: () => {}, info: () => {} },
  dismiss: () => {},
};

export function useToast(): ToastContextValue {
  return useContext(ToastContext) ?? NOOP_TOAST;
}

const VARIANT_ICON: Record<ToastVariant, typeof Info> = {
  error: XCircle,
  success: CheckCircle2,
  info: Info,
};

// Icon carries the status; the card itself is the same raised surface for every variant.
const VARIANT_ICON_CLS: Record<ToastVariant, string> = {
  error: "text-danger",
  success: "text-success",
  info: "text-accent-text",
};

function Toaster({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: number) => void }) {
  const { t } = useTranslation();
  if (toasts.length === 0) return null;
  return (
    <div
      className="pointer-events-none fixed bottom-6 right-6 z-toast flex max-w-[calc(100vw-3rem)] flex-col items-end gap-2"
      aria-live="polite"
    >
      {toasts.map((tn) => {
        const Icon = VARIANT_ICON[tn.variant];
        return (
          <div
            key={tn.id}
            role={tn.variant === "error" ? "alert" : "status"}
            className={cn(
              "pointer-events-auto flex min-w-[280px] max-w-[420px] items-center gap-2.5 rounded-xl bg-surface-raised px-3.5 py-2.5 text-sm text-text shadow-overlay",
              "animate-in fade-in-0 slide-in-from-bottom-2 duration-slow ease-out",
            )}
          >
            <Icon className={cn("size-[15px] shrink-0", VARIANT_ICON_CLS[tn.variant])} />
            <span className="flex-1 break-words">{tn.message}</span>
            <button
              type="button"
              onClick={() => onDismiss(tn.id)}
              className="-mr-1.5 ml-1 inline-flex size-6 shrink-0 items-center justify-center rounded-item text-text-subtle transition-colors duration-fast hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
              aria-label={t("common.dismiss")}
            >
              <X className="size-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
