// frontend/src/components/knowledge/KnowledgeIndexStatus.tsx
//
// Says when ranked search is degraded, and offers the fix (spec knowledge
// FR-060/FR-061): `available: false` means no internal connection is
// configured — that is a Settings problem, so this points there rather than
// offering a rebuild that cannot help. Otherwise, a rebuild is offered only
// when the sidecar is genuinely behind (`files_indexed < files_total`).
// Quiet — renders nothing — once everything is indexed and available; FR-061
// asks the UI to SAY when the index is stale or absent, not to nag once it
// isn't.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { RefreshCw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useIndexStatus, useRebuildIndex } from "@/kinds/knowledge/useKnowledge";

export function KnowledgeIndexStatus() {
  const { t } = useTranslation();
  const status = useIndexStatus();
  const rebuild = useRebuildIndex();

  if (status.isPending || status.error || !status.data) return null;

  const { available, files_indexed, files_total } = status.data;
  const stale = files_indexed < files_total;
  if (available && !stale) return null;

  return (
    <Alert data-testid="knowledge-index-status">
      <AlertTitle>
        {available ? t("knowledge.index.staleTitle") : t("knowledge.index.unavailableTitle")}
      </AlertTitle>
      <AlertDescription className="space-y-2">
        {available ? (
          <>
            <p>
              {t("knowledge.index.staleBody", { indexed: files_indexed, total: files_total })}
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => rebuild.mutate()}
              disabled={rebuild.isPending}
            >
              <RefreshCw
                className={
                  rebuild.isPending ? "mr-1.5 size-3.5 animate-spin" : "mr-1.5 size-3.5"
                }
              />
              {rebuild.isPending ? t("knowledge.index.rebuilding") : t("knowledge.index.rebuild")}
            </Button>
          </>
        ) : (
          <>
            <p>{t("knowledge.index.unavailableBody")}</p>
            <Button asChild size="sm" variant="outline">
              <Link to="/settings/engine">{t("knowledge.index.goToSettings")}</Link>
            </Button>
          </>
        )}
      </AlertDescription>
    </Alert>
  );
}
