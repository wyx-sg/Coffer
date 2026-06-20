// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailHeader.tsx
//
// KB detail header matching the sibling detail pages (agent/mcp): a back link
// to the list, then the title + metric badges on one row with the Settings /
// Reindex / Upload actions on the right. Presentational — the page owns data
// and the action triggers.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  RefreshCw,
  Settings as SettingsIcon,
  TriangleAlert,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";
import type { KnowledgeBaseMetrics } from "./api";

interface Props {
  name: string;
  metrics: KnowledgeBaseMetrics | undefined;
  isReindexPending: boolean;
  isUploadPending: boolean;
  canOpenSettings: boolean;
  onReindex: () => void;
  onOpenSettings: () => void;
  onUpload: () => void;
}

export function KnowledgeBaseDetailHeader({
  name,
  metrics,
  isReindexPending,
  isUploadPending,
  canOpenSettings,
  onReindex,
  onOpenSettings,
  onUpload,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <header className="space-y-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/knowledge-bases")}
        className="-ml-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" /> {t("knowledgeBases.detail.back")}
      </Button>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-serif text-3xl tracking-tight">{name}</h1>
          {metrics ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="secondary">
                {t("knowledgeBases.detail.docBadge", { count: metrics.document_count })}
              </Badge>
              <Badge variant="secondary">
                {t("knowledgeBases.detail.chunkBadge", { count: metrics.chunk_count })}
              </Badge>
              <Badge variant="secondary">{formatBytes(metrics.disk_bytes)}</Badge>
              {metrics.indexed_modes.map((m) => (
                <Badge key={m} variant="outline">
                  {t(`knowledgeBases.modes.${m}`)}
                </Badge>
              ))}
              {metrics.documents_degraded > 0 ? (
                <Badge variant="outline" className="gap-1 text-amber-600 dark:text-amber-500">
                  <TriangleAlert className="size-3" />
                  {t("knowledgeBases.detail.degradedBadge", {
                    count: metrics.documents_degraded,
                  })}
                </Badge>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={onOpenSettings} disabled={!canOpenSettings}>
            <SettingsIcon className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.settings")}
          </Button>
          <Button variant="outline" size="sm" onClick={onReindex} disabled={isReindexPending}>
            <RefreshCw className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.reindex")}
          </Button>
          <Button size="sm" onClick={onUpload} disabled={isUploadPending}>
            <Upload className="mr-1.5 size-3.5" /> {t("knowledgeBases.detail.upload")}
          </Button>
        </div>
      </div>
    </header>
  );
}
