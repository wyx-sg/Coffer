// frontend/src/kinds/memory/MemoryDetailHeader.tsx
//
// Memory store detail header matching the sibling detail pages: a back link to
// the store list, then the store name + scope/metric badges on one row with the
// "Add fact" action on the right (the form lives in a dialog). Presentational.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/utils";
import { deriveScope, storeDisplayName, type MemoryStoreMetrics, type MemoryStoreOut } from "./api";

interface Props {
  store: string;
  storeResource: MemoryStoreOut | undefined;
  metrics: MemoryStoreMetrics | undefined;
  isClearPending: boolean;
  onClearAll: () => void;
  onRename: () => void;
}

export function MemoryDetailHeader({
  store,
  storeResource,
  metrics,
  isClearPending,
  onClearAll,
  onRename,
}: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const scope = storeResource ? deriveScope(storeResource) : null;
  // Readable identity: a user-set label (FR-017c), else the project_root
  // basename (FR-017a), else a graceful placeholder for an orphan store — never
  // the opaque project-<ULID> as the title. While loading, show the raw name.
  const displayName = storeResource
    ? (storeDisplayName(storeResource) ?? t("memory.unnamedStore"))
    : store;
  const projectRoot = storeResource?.project_root ?? null;

  return (
    <header className="space-y-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/memory")}
        className="-ml-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" /> {t("memory.detail.back")}
      </Button>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-serif text-3xl tracking-tight">{displayName}</h1>
          <Button
            variant="ghost"
            size="sm"
            className="-ml-1 text-muted-foreground hover:text-foreground"
            onClick={onRename}
            disabled={!storeResource}
            aria-label={t("memory.rename.title")}
          >
            <Pencil className="size-4" />
          </Button>
          <div className="flex flex-wrap items-center gap-1.5">
            {scope ? <Badge variant="secondary">{t(`memory.scope.${scope}`)}</Badge> : null}
            {metrics ? (
              <>
                <Badge variant="outline">
                  {t("memory.detail.factBadge", { count: metrics.fact_count })}
                </Badge>
                <Badge variant="outline">{formatBytes(metrics.disk_bytes)}</Badge>
              </>
            ) : null}
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
          onClick={onClearAll}
          disabled={isClearPending || (metrics?.fact_count ?? 0) === 0}
        >
          <Trash2 className="mr-1.5 size-3.5" /> {t("memory.detail.clearAll")}
        </Button>
      </div>

      {projectRoot ? (
        <p className="truncate font-mono text-xs text-muted-foreground">{projectRoot}</p>
      ) : null}
    </header>
  );
}
