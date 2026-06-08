// frontend/src/kinds/knowledge_base/KnowledgeBaseMetricsHeader.tsx
//
// KB detail header: the store name + metrics line, a Reindex action, and the
// most recent reindex result. Presentational — all data and the reindex
// trigger are owned by the page.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";
import { type KnowledgeBaseMetrics, type ReindexResult } from "./api";

interface Props {
  name: string;
  metrics: KnowledgeBaseMetrics | undefined;
  reindexResult: ReindexResult | undefined;
  isReindexPending: boolean;
  onReindex: () => void;
}

export function KnowledgeBaseMetricsHeader({
  name,
  metrics,
  reindexResult,
  isReindexPending,
  onReindex,
}: Props) {
  const { t } = useTranslation();
  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">{name}</h1>
          {metrics ? (
            <p className="text-sm text-muted-foreground">
              {t("knowledgeBases.detail.metrics", {
                docs: metrics.document_count,
                chunks: metrics.chunk_count,
                bytes: formatBytes(metrics.disk_bytes),
              })}
              {metrics.indexed_modes.length > 0 ? ` · ${metrics.indexed_modes.join(", ")}` : null}
            </p>
          ) : null}
        </div>
        <Button variant="outline" size="sm" onClick={onReindex} disabled={isReindexPending}>
          {isReindexPending ? t("common.saving") : t("knowledgeBases.detail.reindex")}
        </Button>
      </header>

      {reindexResult ? (
        <p className="text-xs text-muted-foreground">
          {t("knowledgeBases.detail.reindexResult", {
            scanned: reindexResult.documents_scanned,
            reindexed: reindexResult.documents_reindexed,
            skipped: reindexResult.documents_skipped,
          })}
        </p>
      ) : null}
    </>
  );
}
