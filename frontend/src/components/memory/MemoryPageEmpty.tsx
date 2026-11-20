// frontend/src/components/memory/MemoryPageEmpty.tsx
//
// The Memory page in place of its projects: the state could not be read (with
// Retry), or no agent has written a memory yet.
import { useTranslation } from "react-i18next";
import { Brain } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  /** The read's error; `null` means there are no memories yet. */
  error: unknown;
  onRetry: () => void;
}

export function MemoryPageEmpty({ error, onRetry }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 flex-1 items-start justify-center overflow-y-auto px-8 pb-20 pt-10">
      {error ? (
        <EmptyState
          icon={Brain}
          tone="error"
          title={t("memory.loadFailed")}
          description={translateApiError(t, error)}
          action={<Button onClick={onRetry}>{t("common.retry")}</Button>}
        />
      ) : (
        <EmptyState
          icon={Brain}
          title={t("memory.empty.title")}
          description={t("memory.empty.body")}
        />
      )}
    </div>
  );
}
