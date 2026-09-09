// frontend/src/kinds/knowledge/KnowledgeLoadStatus.tsx
//
// Inline load/error status line for the Documents lane: an error alert when
// either backing query failed, a loading hint while either is pending.
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";

export function KnowledgeLoadStatus({
  error,
  isLoading,
}: {
  error: Error | null;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {translateApiError(t, error)}
      </p>
    );
  }
  if (isLoading) {
    return <p className="text-sm text-muted-foreground">{t("common.loading")}</p>;
  }
  return null;
}
