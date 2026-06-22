// components/settings/EmbeddingPanels.tsx — presentational pieces of the global
// Embedding settings card (spec 006): the configured-model summary row (or an
// empty hint) and the chunking-defaults block that also hosts the enable
// switch. Kept apart from EmbeddingSettings so the page stays small.
import type { KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export function EmbeddingModelRow({
  hasModel,
  model,
  provider,
  dimensions,
  onEdit,
}: {
  hasModel: boolean;
  model: string;
  provider: string;
  dimensions: number;
  onEdit: () => void;
}) {
  const { t } = useTranslation();
  if (!hasModel) {
    return (
      <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
        {t("settings.embedding.empty")}
      </p>
    );
  }
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{model}</p>
        <p className="text-xs text-muted-foreground">
          {provider} · {dimensions}d
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={onEdit}>
        <Pencil className="mr-1 size-3.5" />
        {t("settings.embedding.edit")}
      </Button>
    </div>
  );
}

export function EmbeddingChunkingFields({
  enabled,
  onEnabledChange,
  chunkSize,
  onChunkSizeChange,
  onChunkSizeCommit,
  chunkOverlap,
  onChunkOverlapChange,
  onChunkOverlapCommit,
  disabled,
}: {
  enabled: boolean;
  onEnabledChange: (v: boolean) => void;
  chunkSize: number;
  onChunkSizeChange: (v: number) => void;
  /** Persist the chunk size once editing finishes (blur / Enter). */
  onChunkSizeCommit: () => void;
  chunkOverlap: number;
  onChunkOverlapChange: (v: number) => void;
  /** Persist the chunk overlap once editing finishes (blur / Enter). */
  onChunkOverlapCommit: () => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  // Blur on Enter so the commit handler fires from a single code path.
  const commitOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };
  return (
    <div className="space-y-3 border-t border-border pt-4">
      <div>
        <Label>{t("settings.embedding.chunkingTitle")}</Label>
        <p className="text-xs text-muted-foreground">{t("settings.embedding.chunkingHint")}</p>
      </div>

      <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
        <div>
          <Label>{t("settings.embedding.enabled")}</Label>
          <p className="text-xs text-muted-foreground">{t("settings.embedding.enabledHint")}</p>
        </div>
        <Switch checked={enabled} onCheckedChange={onEnabledChange} disabled={disabled} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="emb-chunk-size">{t("settings.embedding.chunkSize")}</Label>
          <Input
            id="emb-chunk-size"
            type="number"
            value={chunkSize}
            disabled={disabled}
            onChange={(e) => onChunkSizeChange(Number(e.target.value) || 0)}
            onBlur={onChunkSizeCommit}
            onKeyDown={commitOnEnter}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="emb-chunk-overlap">{t("settings.embedding.chunkOverlap")}</Label>
          <Input
            id="emb-chunk-overlap"
            type="number"
            value={chunkOverlap}
            disabled={disabled}
            onChange={(e) => onChunkOverlapChange(Number(e.target.value) || 0)}
            onBlur={onChunkOverlapCommit}
            onKeyDown={commitOnEnter}
          />
        </div>
      </div>
    </div>
  );
}
