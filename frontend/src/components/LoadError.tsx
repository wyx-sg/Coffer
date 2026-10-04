// src/components/LoadError.tsx — a failed read inside a card, section or pane: the readable message and a Retry.
//
// For the small spots where a full `EmptyState tone="error"` would be too much
// (one settings block, one file pane): the message in the danger tone, and the
// one next step every failure owes the user. A bare red line is a dead end.
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

interface Props {
  error: unknown;
  onRetry: () => void;
  className?: string;
}

export function LoadError({ error, onRetry, className }: Props) {
  const { t } = useTranslation();
  return (
    <div role="alert" className={cn("flex flex-wrap items-center gap-x-3 gap-y-1", className)}>
      <p className="min-w-0 text-sm text-danger">{translateApiError(t, error)}</p>
      <Button type="button" variant="ghost" size="sm" onClick={onRetry}>
        <RotateCcw aria-hidden /> {t("common.retry")}
      </Button>
    </div>
  );
}
