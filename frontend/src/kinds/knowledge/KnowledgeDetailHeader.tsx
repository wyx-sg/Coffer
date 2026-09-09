// frontend/src/kinds/knowledge/KnowledgeDetailHeader.tsx
//
// Header for one knowledge scope, merging what the two former detail headers
// showed: a back link to the list, the scope's readable name + rename pencil,
// the scope badge, and BOTH lanes' counts side by side — entries an agent
// wrote and documents someone ingested are separate numbers and are never
// summed. Settings / Check sources / Reindex / Upload sit on the right.
// Presentational — the page owns the data and the action triggers.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  FileSearch,
  Pencil,
  RefreshCw,
  Settings as SettingsIcon,
  TriangleAlert,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";
import { deriveScope, scopeDisplayName, type ScopeMetrics, type ScopeOut } from "./api";

interface Props {
  scope: string;
  scopeResource: ScopeOut | undefined;
  metrics: ScopeMetrics | undefined;
  isReindexPending: boolean;
  isUploadPending: boolean;
  checkingSources: boolean;
  onRename: () => void;
  onOpenSettings: () => void;
  onCheckSources: () => void;
  onReindex: () => void;
  onUpload: () => void;
}

export function KnowledgeDetailHeader({
  scope,
  scopeResource,
  metrics,
  isReindexPending,
  isUploadPending,
  checkingSources,
  onRename,
  onOpenSettings,
  onCheckSources,
  onReindex,
  onUpload,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const kind = scopeResource ? deriveScope(scopeResource) : null;
  // Readable identity: a user-set label, else the project_root basename, else
  // the scope's own (already readable) name — never the opaque project-<ULID>
  // as the title. While loading, show the raw scope name.
  const displayName = scopeResource
    ? (scopeDisplayName(scopeResource) ?? t("knowledge.unnamedScope"))
    : scope;
  const projectRoot = scopeResource?.project_root ?? null;
  const hasScope = Boolean(scopeResource);

  return (
    <header className="space-y-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/knowledge")}
        className="-ml-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" /> {t("knowledge.detail.back")}
      </Button>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-serif text-3xl tracking-tight">{displayName}</h1>
          <Button
            variant="ghost"
            size="sm"
            className="-ml-1 text-muted-foreground hover:text-foreground"
            onClick={onRename}
            disabled={!hasScope}
            aria-label={t("knowledge.rename.title")}
          >
            <Pencil className="size-4" />
          </Button>
          <div className="flex flex-wrap items-center gap-1.5">
            {kind ? <Badge variant="secondary">{t(`knowledge.scope.${kind}`)}</Badge> : null}
            {metrics ? (
              <>
                {/* Two lanes, two counts — never one summed total. */}
                <Badge variant="outline">
                  {t("knowledge.detail.entryBadge", { count: metrics.entry_count })}
                </Badge>
                <Badge variant="outline">
                  {t("knowledge.detail.docBadge", { count: metrics.document_count })}
                </Badge>
                <Badge variant="outline">
                  {t("knowledge.detail.chunkBadge", { count: metrics.chunk_count })}
                </Badge>
                <Badge variant="outline">{formatBytes(metrics.disk_bytes)}</Badge>
                {metrics.indexed_modes.map((m) => (
                  <Badge key={m} variant="outline">
                    {t(`knowledge.modes.${m}`)}
                  </Badge>
                ))}
                {metrics.documents_degraded > 0 ? (
                  <Badge variant="outline" className="gap-1 text-amber-600 dark:text-amber-500">
                    <TriangleAlert className="size-3" />
                    {t("knowledge.detail.degradedBadge", { count: metrics.documents_degraded })}
                  </Badge>
                ) : null}
              </>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={onOpenSettings} disabled={!hasScope}>
            <SettingsIcon className="mr-1.5 size-3.5" /> {t("knowledge.detail.settings")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onCheckSources}
            disabled={checkingSources || !hasScope}
          >
            <FileSearch className="mr-1.5 size-3.5" /> {t("knowledge.detail.checkSources")}
          </Button>
          <Button variant="outline" size="sm" onClick={onReindex} disabled={isReindexPending}>
            <RefreshCw className="mr-1.5 size-3.5" /> {t("knowledge.detail.reindex")}
          </Button>
          <Button size="sm" onClick={onUpload} disabled={isUploadPending}>
            <Upload className="mr-1.5 size-3.5" /> {t("knowledge.detail.upload")}
          </Button>
        </div>
      </div>

      {projectRoot ? (
        <p className="truncate font-mono text-xs text-muted-foreground">{projectRoot}</p>
      ) : null}
    </header>
  );
}
