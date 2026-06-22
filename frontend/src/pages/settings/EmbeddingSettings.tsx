// frontend/src/pages/settings/EmbeddingSettings.tsx
//
// The global embedding configuration (Settings → Embedding). One config drives
// vector retrieval everywhere; turning it off (or leaving the model blank)
// falls back to keyword/grep. The single embedding model is configured through
// an Add/Edit dialog (mirroring the LLM connection dialog) — changing the model
// re-embeds every store, so a confirmation guards it. The enable switch lives
// next to the chunking defaults, separate from the model itself.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  EmbeddingModelDialog,
  type EmbeddingModelValues,
} from "@/components/settings/EmbeddingModelDialog";
import {
  EmbeddingChunkingFields,
  EmbeddingModelRow,
} from "@/components/settings/EmbeddingPanels";
import { translateApiError } from "@/lib/api/errors";
import { useEmbeddingConfig, useUpdateEmbeddingConfig } from "@/lib/hooks/useEmbeddingConfig";

export function EmbeddingSettings() {
  const { t } = useTranslation();
  const { data, isPending, error } = useEmbeddingConfig();
  const update = useUpdateEmbeddingConfig();

  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState("local");
  const [model, setModel] = useState("");
  const [dimensions, setDimensions] = useState(768);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [credentialRef, setCredentialRef] = useState<string | null>(null);
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(64);

  const [dialogOpen, setDialogOpen] = useState(false);
  // Holds the pending model values while the change-model confirmation is shown.
  const [confirm, setConfirm] = useState<EmbeddingModelValues | null>(null);

  // Seed the form from the loaded config once it arrives.
  useEffect(() => {
    if (!data) return;
    setEnabled(data.enabled);
    setProvider(data.provider ?? "local");
    setModel(data.model ?? "");
    setDimensions(data.dimensions);
    setBaseUrl(data.base_url ?? null);
    setCredentialRef(data.credential_ref ?? null);
    setChunkSize(data.default_chunk_size);
    setChunkOverlap(data.default_chunk_overlap);
  }, [data]);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-6">{t("common.loading")}</CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }

  const hasModel = model.trim() !== "";

  // PUT the full config, overriding the model fields with `next` when given.
  const persist = (next?: Partial<EmbeddingModelValues>) => {
    update.mutate({
      enabled,
      provider: (next?.provider ?? provider) || null,
      model: (next?.model ?? model).trim() || null,
      dimensions: next?.dimensions ?? dimensions,
      base_url: next === undefined ? baseUrl : (next.base_url ?? null),
      credential_ref: next === undefined ? credentialRef : (next.credential_ref ?? null),
      default_chunk_size: chunkSize,
      default_chunk_overlap: chunkOverlap,
    });
  };

  // Commit model values from the dialog into local state + persist.
  const commitModel = (v: EmbeddingModelValues) => {
    setProvider(v.provider);
    setModel(v.model);
    setDimensions(v.dimensions);
    setBaseUrl(v.base_url);
    setCredentialRef(v.credential_ref);
    persist(v);
    setDialogOpen(false);
  };

  // From the dialog: changing the model, its dimensions, or the provider of an
  // already-set model re-embeds every store (a width change even rebuilds the
  // vec table), so confirm first; first-time configuration commits directly.
  const onDialogSubmit = (v: EmbeddingModelValues) => {
    const reEmbeds =
      v.model.trim() !== model.trim() ||
      v.dimensions !== dimensions ||
      v.provider !== provider;
    if (hasModel && reEmbeds) {
      setConfirm(v);
      setDialogOpen(false);
      return;
    }
    commitModel(v);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle>{t("settings.embedding.title")}</CardTitle>
        {!hasModel && (
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="mr-1 size-4" />
            {t("settings.embedding.add")}
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("settings.embedding.description")}</p>

        <EmbeddingModelRow
          hasModel={hasModel}
          model={model}
          provider={provider}
          dimensions={dimensions}
          onEdit={() => setDialogOpen(true)}
        />

        <EmbeddingChunkingFields
          enabled={enabled}
          onEnabledChange={setEnabled}
          chunkSize={chunkSize}
          onChunkSizeChange={setChunkSize}
          chunkOverlap={chunkOverlap}
          onChunkOverlapChange={setChunkOverlap}
        />

        {update.error ? (
          <p className="text-sm text-destructive" role="alert">
            {translateApiError(t, update.error)}
          </p>
        ) : null}

        <div className="flex justify-end">
          <Button onClick={() => persist()} disabled={update.isPending}>
            {update.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </CardContent>

      <Dialog open={dialogOpen} onOpenChange={(open) => !open && setDialogOpen(false)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {hasModel ? t("settings.embedding.editTitle") : t("settings.embedding.addTitle")}
            </DialogTitle>
          </DialogHeader>
          <EmbeddingModelDialog
            initial={{
              provider,
              model,
              dimensions,
              base_url: baseUrl,
              credential_ref: credentialRef,
            }}
            pending={update.isPending}
            onSubmit={onDialogSubmit}
            onCancel={() => setDialogOpen(false)}
          />
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={t("settings.embedding.changeModelTitle")}
        description={t("settings.embedding.changeModelConfirm")}
        confirmLabel={t("settings.embedding.changeModelConfirmLabel")}
        variant="default"
        pending={update.isPending}
        onConfirm={() => {
          if (confirm) commitModel(confirm);
          setConfirm(null);
        }}
      />
    </Card>
  );
}
