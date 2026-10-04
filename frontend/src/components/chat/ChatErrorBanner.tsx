// frontend/src/components/chat/ChatErrorBanner.tsx — the one inline error
// surface for the chat page. A failed turn renders it INSIDE the reply it
// failed, left-aligned with the reply's text (`reply` variant: a title, an
// explanation line, Retry / Dismiss); a failed conversation create renders the
// full-width strip above the draft. Optional Retry re-issues the failed action;
// Dismiss clears it.
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  message: string;
  onDismiss?: () => void;
  /** Re-runs the failed action; the button is shown only when provided. */
  onRetry?: () => void;
  /** The action button's label when it is not a plain Retry (e.g. Resume queue). */
  retryLabel?: string;
  /** Border side and any extra layout classes from the caller. */
  className?: string;
  /** A second, quieter line under the message (the `reply` variant). */
  detail?: string;
  /** `reply`: the boxed banner that sits inside an agent's reply. */
  variant?: "strip" | "reply";
}

export function ChatErrorBanner({
  message,
  onDismiss,
  onRetry,
  retryLabel,
  className,
  detail,
  variant = "strip",
}: Props) {
  const { t } = useTranslation();
  if (variant === "reply") {
    return (
      <div
        role="alert"
        className={cn(
          "flex items-start gap-3 rounded-lg border border-danger/30 bg-danger-soft px-3.5 py-3",
          className,
        )}
      >
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="break-words text-sm font-semibold text-danger">{message}</p>
          {detail ? <p className="text-xs text-text-muted">{detail}</p> : null}
        </div>
        {onRetry ? (
          <Button type="button" variant="outline" size="sm" onClick={onRetry}>
            {retryLabel ?? t("common.retry")}
          </Button>
        ) : null}
        {onDismiss ? (
          <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
            {t("common.dismiss")}
          </Button>
        ) : null}
      </div>
    );
  }
  return (
    <div
      role="alert"
      className={cn(
        "flex items-center gap-3 border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive",
        className,
      )}
    >
      <AlertCircle className="size-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 break-words">{message}</span>
      {onRetry ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 shrink-0 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={onRetry}
        >
          {retryLabel ?? t("common.retry")}
        </Button>
      ) : null}
      {onDismiss ? (
        <button
          type="button"
          className="shrink-0 font-medium underline-offset-2 hover:underline"
          onClick={onDismiss}
        >
          {t("common.dismiss")}
        </button>
      ) : null}
    </div>
  );
}
