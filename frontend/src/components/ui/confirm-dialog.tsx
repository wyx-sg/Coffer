// src/components/ui/confirm-dialog.tsx
// The one confirmation dialog (it replaced native window.confirm).
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
//   • `onConfirm` returns a PROMISE — the dialog closes when it resolves, and
//     on rejection stays open and renders the reason. Nothing else to wire.
//   • `onConfirm` returns nothing — the caller closes in its own `onSuccess`
//     and passes its mutation's `error` in, which is the same behaviour with
//     the state in the caller's hands.
//
// A failure never closes silently either way: whatever is shown comes from
// `error` if the caller supplies one, and from the rejection otherwise, so the
// dialog is never left open with no explanation for why it did not go through.
import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle } from "lucide-react";
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
  title: string;
  description?: string;
  /** Confirm-button label; defaults to common.delete via the caller. */
  confirmLabel: string;
  /** Visual intent of the confirm button. */
  variant?: "destructive" | "default";
  /** Rendered under the description, for the times a sentence cannot say what
   *  is about to happen — the list of paths a destructive action would take
   *  with it. Naming them is the difference between a warning and a question
   *  the user can actually answer. */
  children?: ReactNode;
  /** Disables the confirm button (e.g. while the mutation is pending). */
  pending?: boolean;
  /** A failure to show inline — typically a mutation's `error`. While one is
   *  shown the dialog stays open, so the user can read it and retry. */
  error?: unknown;
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
  variant = "destructive",
  pending = false,
  error,
  onConfirm,
  children,
}: Props) {
  const { t } = useTranslation();
  // A rejection the caller did not hand us as `error`. Cleared when the dialog
  // closes, so reopening it never shows the previous attempt's failure.
  const [rejection, setRejection] = useState<unknown>(null);
  useEffect(() => {
    if (!open) setRejection(null);
  }, [open]);

  const failure = error ?? rejection;

  const confirm = () => {
    setRejection(null);
    const result = onConfirm();
    if (!isPromise(result)) return;
    void result.then(
      () => onOpenChange(false),
      (reason: unknown) => setRejection(reason ?? new Error("confirm failed")),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        {children}
        {failure ? (
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{translateApiError(t, failure)}</span>
          </div>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button variant={variant} disabled={pending} onClick={confirm}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
