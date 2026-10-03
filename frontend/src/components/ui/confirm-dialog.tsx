// src/components/ui/confirm-dialog.tsx
// The one confirmation dialog (it replaced native window.confirm), for
// destructive or irreversible actions only (Shell · Confirm, 420 wide).
//
// A confirmation CLOSES ONLY ON SUCCESS. That is the convention, and it lives
// here because a primitive that cannot express it is the reason three call
// sites each answered the question differently: one hand-rolled the whole
// Dialog to add an inline error, one closed whatever the outcome, and one was
// a byte-for-byte copy extracted only to fit a file-size budget. So the
// primitive now owns both halves — the error slot, and the closing rule.
//
// `open` stays caller-owned (the caller usually keys it off its own state), so
// the dialog asks to be closed rather than closing itself. Two ways to drive
// it:
//
//   • `onConfirm` returns a PROMISE — the dialog is pending while it runs,
//     closes when it resolves, and on rejection stays open and shows why.
//   • `onConfirm` returns nothing — the caller closes in its own `onSuccess`
//     and passes its mutation's `pending` and `error` in, which is the same
//     behaviour with the state in the caller's hands.
//
// Pending: the confirm button spins and reads `pendingLabel` ("Removing…"),
// Cancel is disabled, and every other way out (the ×, Esc, a click outside)
// is ignored — the action has been sent and the dialog must see how it ends.
// Error: an inline banner (title + the translated reason) and the confirm
// button turns into "Try again". A failure never closes silently either way:
// whatever is shown comes from `error` if the caller supplies one, and from
// the rejection otherwise.
import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The question, naming the object: "Delete sentry?". */
  title: string;
  description?: string;
  /** Confirm-button label; defaults to common.delete via the caller. */
  confirmLabel: string;
  /** Leading icon of the confirm button (the board's trash on "Delete server"). */
  confirmIcon?: ReactNode;
  /** Visual intent of the confirm button. */
  variant?: "destructive" | "default";
  /** Rendered under the description: what the action takes with it — see
   *  `ConfirmFacts` for the label/value list the boards use. Naming them is
   *  the difference between a warning and a question the user can answer. */
  children?: ReactNode;
  /** The caller's mutation is running (see "Pending" above). */
  pending?: boolean;
  /** The confirm label while pending ("Deleting…"); defaults to "Working…".
   *  `confirmLabel` stays the resting label — a caller never swaps it itself. */
  pendingLabel?: string;
  /** The confirm button is unavailable until the user has done what the dialog
   *  asks first (typing the name); not a pending state, so no spinner. */
  confirmDisabled?: boolean;
  /** A failure to show inline — typically a mutation's `error`. While one is
   *  shown the dialog stays open, so the user can read it and retry. */
  error?: unknown;
  /** The banner's title over the reason ("Couldn’t delete sentry"): every
   *  destructive dialog names the verb and the object. Without one the banner
   *  reads "Couldn’t finish that". */
  errorTitle?: string;
  /** The confirm label after a failure; defaults to "Try again". */
  retryLabel?: string;
  /** The Cancel button's label, when the question wants its own words ("Keep editing"). */
  cancelLabel?: string;
  /** Returning a promise hands the closing rule to this dialog: resolve closes
   *  it, reject keeps it open with the reason shown. Returning nothing leaves
   *  the closing to the caller. */
  onConfirm: () => void | Promise<unknown>;
}

function isPromise(value: unknown): value is Promise<unknown> {
  return typeof (value as Promise<unknown> | undefined)?.then === "function";
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  confirmIcon,
  variant = "destructive",
  pending = false,
  pendingLabel,
  confirmDisabled = false,
  error,
  errorTitle,
  retryLabel,
  cancelLabel,
  onConfirm,
  children,
}: Props) {
  const { t } = useTranslation();
  // A rejection the caller did not hand us as `error`, and whether our own
  // promise is still running. Cleared when the dialog closes, so reopening it
  // never shows the previous attempt.
  const [rejection, setRejection] = useState<unknown>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (!open) {
      setRejection(null);
      setRunning(false);
    }
  }, [open]);

  const busy = pending || running;
  const failure = error ?? rejection;

  const confirm = () => {
    if (busy) return;
    setRejection(null);
    const result = onConfirm();
    if (!isPromise(result)) return;
    setRunning(true);
    void result.then(
      () => {
        setRunning(false);
        onOpenChange(false);
      },
      (reason: unknown) => {
        setRunning(false);
        setRejection(reason ?? new Error("confirm failed"));
      },
    );
  };

  // While the action runs, no way out: the ×, Esc and outside clicks all
  // arrive here as a close request and are dropped.
  const requestOpenChange = (next: boolean) => {
    if (!next && busy) return;
    onOpenChange(next);
  };
  const holdWhileBusy = (e: Event) => {
    if (busy) e.preventDefault();
  };

  return (
    <Dialog open={open} onOpenChange={requestOpenChange}>
      <DialogContent
        className="max-w-[420px]"
        onEscapeKeyDown={holdWhileBusy}
        onInteractOutside={holdWhileBusy}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
        {failure ? (
          <DialogErrorBanner
            title={errorTitle ?? t("common.actionFailed")}
            message={translateApiError(t, failure)}
          />
        ) : null}
        <DialogFooter>
          <Button variant="ghost" disabled={busy} onClick={() => onOpenChange(false)}>
            {cancelLabel ?? t("common.cancel")}
          </Button>
          <Button variant={variant} loading={busy} disabled={confirmDisabled} onClick={confirm}>
            {busy ? null : failure ? <RotateCw aria-hidden /> : confirmIcon}
            {busy
              ? (pendingLabel ?? t("common.working"))
              : failure
                ? (retryLabel ?? t("common.tryAgain"))
                : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The inline error of a dialog (Foundations · Feedback · Banner · error):
 *  danger-soft fill, r8, p 10 12, a 15px danger icon, a 13/550 title and a
 *  12px muted reason. Exported for any dialog that reports a failure in place. */
export function DialogErrorBanner({ title, message }: { title: string; message: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5" role="alert">
      <AlertTriangle aria-hidden className="mt-px size-[15px] shrink-0 stroke-[1.75] text-danger" />
      <div className="flex min-w-0 flex-col gap-[3px]">
        <span className="text-sm font-label text-text">{title}</span>
        <span className="break-words text-xs leading-[1.45] text-text-muted">{message}</span>
      </div>
    </div>
  );
}

/** The consequence list of a confirmation: label (12, subtle) / value (13)
 *  rows split by hairlines, as the Delete boards lay them out. */
export function ConfirmFacts({ items }: { items: { label: ReactNode; value: ReactNode }[] }) {
  return (
    <dl className="flex flex-col">
      {items.map((item, i) => (
        <div
          key={i}
          className="grid grid-cols-[70px_minmax(0,1fr)] items-baseline gap-4 border-t border-border-subtle py-[7px]"
        >
          <dt className="text-xs text-text-subtle">{item.label}</dt>
          <dd className="min-w-0 text-sm text-text [overflow-wrap:anywhere]">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
