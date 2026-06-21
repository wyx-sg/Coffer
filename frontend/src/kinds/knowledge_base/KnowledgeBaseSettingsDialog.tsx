// frontend/src/kinds/knowledge_base/KnowledgeBaseSettingsDialog.tsx
//
// Post-creation KB config editing: chunking (chunk_size / chunk_overlap) and a
// vector-search toggle (adds/removes "vector" from enabled_modes). The
// embedding model/provider is GLOBAL now — configured once in Settings →
// Embedding, not per knowledge base. Presentational — the page owns the PATCH
// mutation; on submit this builds the FULL merged config (the backend replaces,
// not deep-merges) and hands it to onSubmit.
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
import type { KnowledgeBaseConfigOut, RetrievalMode } from "./api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The KB's current config; seeds the form (mount fresh per open). */
  config: KnowledgeBaseConfigOut;
  error: unknown;
  isPending: boolean;
  onSubmit: (config: KnowledgeBaseConfigOut) => void;
}

export function KnowledgeBaseSettingsDialog({
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
  const [vectorEnabled, setVectorEnabled] = useState(config.enabled_modes.includes("vector"));
  const [autoUpdateSources, setAutoUpdateSources] = useState(config.auto_update_sources);

  const submit = () => {
    const baseModes: RetrievalMode[] = config.enabled_modes.filter((m) => m !== "vector");
    onSubmit({
      ...config,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      enabled_modes: vectorEnabled ? [...baseModes, "vector"] : baseModes,
      // Carried through explicitly: the PATCH replaces the whole config, so
      // omitting this would reset auto-update to false on every save.
      auto_update_sources: autoUpdateSources,
      // Embedding is global (Settings → Embedding); the KB config no longer
      // carries it.
      embedding: null,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledgeBases.settings.title")}</DialogTitle>
          <DialogDescription>{t("knowledgeBases.settings.description")}</DialogDescription>
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
              <Label htmlFor="kb-chunk-size">{t("knowledgeBases.settings.chunkSize")}</Label>
              <Input
                id="kb-chunk-size"
                type="number"
                min={1}
                value={chunkSize}
                onChange={(e) => setChunkSize(Number(e.target.value) || config.chunk_size)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="kb-chunk-overlap">{t("knowledgeBases.settings.chunkOverlap")}</Label>
              <Input
                id="kb-chunk-overlap"
                type="number"
                min={0}
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
              />
            </div>
          </div>
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="kb-settings-vector">{t("knowledgeBases.dialog.vector")}</Label>
              <p className="text-xs text-muted-foreground">
                {t("knowledgeBases.settings.vectorHint")}
              </p>
            </div>
            <Switch
              id="kb-settings-vector"
              checked={vectorEnabled}
              onCheckedChange={setVectorEnabled}
            />
          </div>
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="kb-settings-auto-update">
                {t("knowledgeBases.settings.autoUpdateSources")}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t("knowledgeBases.settings.autoUpdateSourcesHint")}
              </p>
            </div>
            <Switch
              id="kb-settings-auto-update"
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
