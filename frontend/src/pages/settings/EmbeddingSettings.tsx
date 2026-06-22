// frontend/src/pages/settings/EmbeddingSettings.tsx
//
// The global embedding configuration (Settings → Embedding). Embedding is no
// longer set per knowledge base / memory store; one config here drives vector
// retrieval everywhere. Turning it off (or leaving the model blank) makes every
// store fall back to keyword/grep.
//
// The model is configured through an Add/Edit dialog (mirroring the LLM
// connection dialog) — there is only ever ONE embedding model. Changing the
// model re-embeds every store, so a confirmation guards that. The enable switch
// lives next to the chunking defaults, separate from the model itself.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  EmbeddingModelDialog,
  type EmbeddingModelValues,
} from "@/components/settings/EmbeddingModelDialog";
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

  // From the dialog: changing an already-set model re-embeds everything, so
  // confirm first; first-time configuration commits directly.
  const onDialogSubmit = (v: EmbeddingModelValues) => {
    if (hasModel && v.model.trim() !== model.trim()) {
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

        {hasModel ? (
          <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{model}</p>
              <p className="text-xs text-muted-foreground">
                {provider} · {dimensions}d
              </p>
            </div>
            <Button variant="secondary" size="sm" onClick={() => setDialogOpen(true)}>
              <Pencil className="mr-1 size-3.5" />
              {t("settings.embedding.edit")}
            </Button>
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
            {t("settings.embedding.empty")}
          </p>
        )}

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
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="emb-chunk-size">{t("settings.embedding.chunkSize")}</Label>
              <Input
                id="emb-chunk-size"
                type="number"
                value={chunkSize}
                onChange={(e) => setChunkSize(Number(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="emb-chunk-overlap">{t("settings.embedding.chunkOverlap")}</Label>
              <Input
                id="emb-chunk-overlap"
                type="number"
                value={chunkOverlap}
                onChange={(e) => setChunkOverlap(Number(e.target.value) || 0)}
              />
            </div>
          </div>
        </div>

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
