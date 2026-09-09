// frontend/src/kinds/knowledge/KnowledgeSettingsDialog.tsx
//
// Per-scope config editing: chunking (chunk_size / chunk_overlap), the vector
// toggle (adds/removes "vector" from retrieval_modes), and auto-update from
// source. There is NO embedding form here — embedding is installation-wide
// (Settings → Embedding), and a scope opts into semantic search purely by
// listing the mode.
//
// Presentational — the page owns the PATCH mutation. The scope PATCH MERGES, so
// this submits only the fields the form owns rather than a full replacement.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { KnowledgeConfigOut, KnowledgeConfigPatch, RetrievalMode } from "./api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The scope's current config; seeds the form (mount fresh per open). */
  config: KnowledgeConfigOut;
  error: unknown;
  isPending: boolean;
  onSubmit: (patch: KnowledgeConfigPatch) => void;
}

export function KnowledgeSettingsDialog({
  open,
  onOpenChange,
  config,
  error,
  isPending,
  onSubmit,
}: Props) {
  const { t } = useTranslation();
  const [chunkSize, setChunkSize] = useState(config.chunk_size);
  const [chunkOverlap, setChunkOverlap] = useState(config.chunk_overlap);
  const [vectorEnabled, setVectorEnabled] = useState(config.retrieval_modes.includes("vector"));
  const [autoUpdateSources, setAutoUpdateSources] = useState(config.auto_update_sources);

  const submit = () => {
    // "vector" is the opt-in; the backend adds "hybrid" alongside it and picks
    // the default mode, so the form only ever sends the base modes ± vector.
    const baseModes: RetrievalMode[] = config.retrieval_modes.filter(
      (m) => m !== "vector" && m !== "hybrid",
    );
    onSubmit({
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      retrieval_modes: vectorEnabled ? [...baseModes, "vector"] : baseModes,
      auto_update_sources: autoUpdateSources,
      // When vector goes away the stored default_mode may no longer be in the
      // list, which the backend rejects — fall back to keyword in that case.
      ...(vectorEnabled || baseModes.includes(config.default_mode)
        ? {}
        : { default_mode: "keyword" as RetrievalMode }),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledge.settings.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.settings.description")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="knowledge-chunk-size">{t("knowledge.settings.chunkSize")}</Label>
              <Input
                id="knowledge-chunk-size"
                type="number"
                min={1}
                value={chunkSize}
                onChange={(e) => setChunkSize(Number(e.target.value) || config.chunk_size)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="knowledge-chunk-overlap">
                {t("knowledge.settings.chunkOverlap")}
              </Label>
              <Input
                id="knowledge-chunk-overlap"
                type="number"
                min={0}
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
              />
            </div>
          </div>
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="knowledge-settings-vector">{t("knowledge.dialog.vector")}</Label>
              <p className="text-xs text-muted-foreground">{t("knowledge.settings.vectorHint")}</p>
            </div>
            <Switch
              id="knowledge-settings-vector"
              checked={vectorEnabled}
              onCheckedChange={setVectorEnabled}
            />
          </div>
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="knowledge-settings-auto-update">
                {t("knowledge.settings.autoUpdateSources")}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t("knowledge.settings.autoUpdateSourcesHint")}
              </p>
            </div>
            <Switch
              id="knowledge-settings-auto-update"
              checked={autoUpdateSources}
              onCheckedChange={setAutoUpdateSources}
            />
          </div>
          {error ? <p className="text-sm text-destructive">{translateApiError(t, error)}</p> : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
