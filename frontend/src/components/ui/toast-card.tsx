// src/components/ui/toast-card.tsx
// The toast stack and its cards (Foundations · Feedback · Toast): bottom-right
// at a 24px inset, min 280 / max 420 wide, p 10 14, r10, the raised surface
// with the overlay shadow, a 15px status icon, one 13/600 action 12px after
// the message. A card that will leave on its own draws a 2px line along its
// bottom edge that shrinks with the time it has left, and stops with the clock
// while the pointer or focus is on the card; an error stays until dismissed
// and draws no line. Timing itself is the provider's
// (toast.tsx); the line is only its picture.
import { useEffect, useRef, useState, type ButtonHTMLAttributes } from "react";
import { AlertTriangle, Check, Info, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

import type { ToastItem, ToastVariant } from "./toast";

/** How many cards show before older ones fold into the "N more" chip. */
export const MAX_VISIBLE_TOASTS = 3;

const VARIANT_ICON: Record<ToastVariant, typeof Info> = {
  error: AlertTriangle,
  success: Check,
  info: Info,
};

// Icon carries the status; the card itself is the same raised surface for every variant.
const VARIANT_ICON_CLS: Record<ToastVariant, string> = {
  error: "text-danger",
  success: "text-success",
  info: "text-text-muted",
};

interface StackProps {
  toasts: ToastItem[];
  onDismiss: (id: number) => void;
  onPause: (id: number) => void;
  onResume: (id: number) => void;
}

export function Toaster({ toasts, onDismiss, onPause, onResume }: StackProps) {
  const { t } = useTranslation();
  const [unfolded, setUnfolded] = useState(false);
  const hidden = Math.max(0, toasts.length - MAX_VISIBLE_TOASTS);
  useEffect(() => {
    if (hidden === 0) setUnfolded(false);
  }, [hidden]);
  if (toasts.length === 0) return null;
  const shown = unfolded ? toasts : toasts.slice(hidden);
  return (
    <div
      className="pointer-events-none fixed bottom-6 right-6 z-toast flex max-h-[calc(100vh-3rem)] max-w-[calc(100vw-3rem)] flex-col items-end gap-2 overflow-y-auto"
      aria-live="polite"
    >
      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => setUnfolded((v) => !v)}
          aria-expanded={unfolded}
          className="pointer-events-auto rounded-full bg-surface-raised px-2.5 py-1 text-xs text-text-muted shadow-overlay transition-colors duration-fast hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          {unfolded ? t("common.lessDetails") : t("common.earlierToasts", { count: hidden })}
        </button>
      ) : null}
      {shown.map((tn) => (
        <ToastCard
          key={tn.id}
          toast={tn}
          onDismiss={() => onDismiss(tn.id)}
          onPause={() => onPause(tn.id)}
          onResume={() => onResume(tn.id)}
        />
      ))}
    </div>
  );
}

interface CardProps {
  toast: ToastItem;
  onDismiss: () => void;
  onPause: () => void;
  onResume: () => void;
}

function ToastCard({ toast, onDismiss, onPause, onResume }: CardProps) {
  const { t } = useTranslation();
  const Icon = VARIANT_ICON[toast.variant];
  const isError = toast.variant === "error";
  const [expanded, setExpanded] = useState(false);
  const hover = useRef(false);
  const focus = useRef(false);
  const line = useTimerLine(toast.duration);

  // Pointer and focus each hold the clock; it runs again only when both let go.
  const hold = (which: typeof hover, on: boolean) => {
    which.current = on;
    if (hover.current || focus.current) {
      onPause();
      line.pause();
    } else {
      onResume();
      line.play();
    }
  };

  // An error always offers a next step: its action if it has one, and the
  // Details toggle when there is more to read — or when there is no action.
  const showDetails = Boolean(toast.details) || (isError && !toast.action);

  return (
    <div
      role={isError ? "alert" : "status"}
      onMouseEnter={() => hold(hover, true)}
      onMouseLeave={() => hold(hover, false)}
      onFocus={() => hold(focus, true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) hold(focus, false);
      }}
      className={cn(
        "group pointer-events-auto relative min-w-[280px] max-w-[420px] overflow-hidden rounded-xl bg-surface-raised text-sm text-text shadow-overlay",
        "animate-in fade-in-0 slide-in-from-bottom-2 duration-slow ease-out",
      )}
    >
      <div className={cn("flex gap-2.5 px-3.5 py-2.5", expanded ? "items-start" : "items-center")}>
        <Icon
          aria-hidden
          className={cn("size-[15px] shrink-0 stroke-[1.75]", VARIANT_ICON_CLS[toast.variant])}
        />
        <div className="min-w-0 flex-1">
          <p className={expanded ? "break-words" : "truncate"}>{toast.message}</p>
          {expanded && toast.details ? (
            <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-[1.45] text-text-muted">
              {toast.details}
            </p>
          ) : null}
        </div>
        {toast.action ? (
          <ActionLink
            onClick={() => {
              toast.action?.onClick();
              onDismiss();
            }}
          >
            {toast.action.label}
          </ActionLink>
        ) : null}
        {showDetails ? (
          <ActionLink onClick={() => setExpanded((v) => !v)} aria-expanded={expanded}>
            {expanded ? t("common.lessDetails") : t("common.details")}
          </ActionLink>
        ) : null}
        <button
          type="button"
          onClick={onDismiss}
          className={cn(
            "-mr-1.5 inline-flex size-6 shrink-0 items-center justify-center rounded-item text-text-subtle transition-[color,background-color,opacity] duration-fast hover:bg-surface-hover hover:text-text focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            // An error has no clock, so its dismiss is always there; a toast that
            // leaves on its own shows it only under the pointer or focus.
            !isError && "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
          )}
          aria-label={t("common.dismiss")}
        >
          <X className="size-3.5" />
        </button>
      </div>
      {toast.duration !== null ? (
        <span
          ref={line.ref}
          aria-hidden
          data-testid="toast-timer"
          className="absolute bottom-0 left-0 h-0.5 w-full origin-left bg-border"
        />
      ) : null}
    </div>
  );
}

function ActionLink({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(
        "ml-3 shrink-0 whitespace-nowrap rounded-xs text-sm font-semibold text-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
        className,
      )}
      {...props}
    />
  );
}

// The shrinking line, driven by the Web Animations API so it can pause in step
// with the clock. Where the API is missing (jsdom) the line simply stays full.
function useTimerLine(duration: number | null) {
  const ref = useRef<HTMLSpanElement>(null);
  const anim = useRef<Animation | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || duration === null || typeof el.animate !== "function") return;
    anim.current = el.animate([{ transform: "scaleX(1)" }, { transform: "scaleX(0)" }], {
      duration,
      easing: "linear",
      fill: "forwards",
    });
    return () => anim.current?.cancel();
  }, [duration]);
  return {
    ref,
    pause: () => anim.current?.pause(),
    play: () => anim.current?.play(),
  };
}
