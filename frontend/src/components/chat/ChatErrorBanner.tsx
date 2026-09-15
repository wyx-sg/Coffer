// frontend/src/components/chat/ChatErrorBanner.tsx — the one inline error
// surface for the chat page: a failed turn above the composer and a failed
// conversation create above the draft both render this, so an error always
// looks the same and sits in the flow (never floating over the thread).
// Optional Retry re-issues the failed action; Dismiss clears it.
import { AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  message: string;
  onDismiss?: () => void;
  /** Re-runs the failed action; the button is shown only when provided. */
  onRetry?: () => void;
  /** Border side and any extra layout classes from the caller. */
  className?: string;
}

export function ChatErrorBanner({ message, onDismiss, onRetry, className }: Props) {
  const { t } = useTranslation();
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
          {t("common.retry")}
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
