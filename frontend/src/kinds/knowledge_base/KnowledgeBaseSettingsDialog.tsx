// frontend/src/kinds/knowledge_base/KnowledgeBaseSettingsDialog.tsx
//
// Post-creation KB config editing (spec 006 FR-019/FR-014): chunking
// (chunk_size / chunk_overlap) and the embedding block (provider / model /
// dimensions / base_url / credential_ref). Mirrors KnowledgeBaseAddDialog's
// vector toggle: enabling it reveals the embedding fields and adds "vector"
// to enabled_modes. Presentational — the page owns the PATCH mutation; on
// submit this builds the FULL merged config (the backend replaces, not
// deep-merges) and hands it to onSubmit.
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

const DEFAULT_PROVIDER = "local";
const DEFAULT_MODEL = "bge-m3";
const DEFAULT_DIMENSIONS = 1024;

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
  const [vectorEnabled, setVectorEnabled] = useState(Boolean(config.embedding));
  const [provider, setProvider] = useState(config.embedding?.provider ?? DEFAULT_PROVIDER);
  const [model, setModel] = useState(config.embedding?.model ?? DEFAULT_MODEL);
  const [baseUrl, setBaseUrl] = useState(config.embedding?.base_url ?? "");
  const [credentialRef, setCredentialRef] = useState(config.embedding?.credential_ref ?? "");
  const [dimensions, setDimensions] = useState(config.embedding?.dimensions ?? DEFAULT_DIMENSIONS);

  const submit = () => {
    const baseModes: RetrievalMode[] = config.enabled_modes.filter((m) => m !== "vector");
    onSubmit({
      ...config,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
      enabled_modes: vectorEnabled ? [...baseModes, "vector"] : baseModes,
      embedding: vectorEnabled
        ? {
            provider,
            model,
            base_url: baseUrl.trim() || null,
            credential_ref: credentialRef.trim() || null,
            dimensions,
          }
        : null,
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
                {t("knowledgeBases.dialog.vectorHint")}
              </p>
            </div>
            <Switch
              id="kb-settings-vector"
              checked={vectorEnabled}
              onCheckedChange={setVectorEnabled}
            />
          </div>
          {vectorEnabled ? (
            <div className="space-y-3 rounded-md border p-3">
              <div className="space-y-2">
                <Label htmlFor="kb-settings-provider">{t("knowledgeBases.dialog.provider")}</Label>
                <Input
                  id="kb-settings-provider"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  placeholder="local | openai | voyage | …"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-settings-model">
                  {t("knowledgeBases.dialog.embeddingModel")}
                </Label>
                <Input
                  id="kb-settings-model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-settings-dimensions">
                  {t("knowledgeBases.dialog.dimensions")}
                </Label>
                <Input
                  id="kb-settings-dimensions"
                  type="number"
                  min={1}
                  value={dimensions}
                  onChange={(e) => setDimensions(Number(e.target.value) || DEFAULT_DIMENSIONS)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-settings-base-url">{t("knowledgeBases.dialog.baseUrl")}</Label>
                <Input
                  id="kb-settings-base-url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://… (optional, OpenAI-compatible)"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-settings-cred">{t("knowledgeBases.dialog.credential")}</Label>
                <Input
                  id="kb-settings-cred"
                  value={credentialRef}
                  onChange={(e) => setCredentialRef(e.target.value)}
                  placeholder="keychain reference (optional)"
                />
              </div>
            </div>
          ) : null}
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
