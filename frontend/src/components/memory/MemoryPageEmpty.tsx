// frontend/src/components/memory/MemoryPageEmpty.tsx
//
// The Memory page in place of its scopes and memories: the sync state could
// not be read (with Retry), or no agent is connected (with a link to Agents).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Brain } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";

interface Props {
  /** The read's error; `null` means no agent is connected. */
  error: unknown;
  onRetry: () => void;
}

export function MemoryPageEmpty({ error, onRetry }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 flex-1 items-start justify-center overflow-y-auto px-8 pb-20">
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
          title={t("memory.noAgents.title")}
          description={t("memory.noAgents.body")}
          action={
            <Button asChild>
              <Link to="/agents">{t("memory.noAgents.open")}</Link>
            </Button>
          }
        />
      )}
    </div>
  );
}
