// frontend/src/pages/settings/EmbeddingSettings.tsx
//
// The global embedding configuration (Settings → Engine). One config drives
// vector retrieval everywhere; turning it off — or naming no connection/model —
// falls back to keyword/grep. The card asks exactly what the internal-engine
// card above it asks: PICK A PROVIDER, then PICK A MODEL (knowledge FR-077).
// There is no add-a-model form and no key field any more — the endpoint, wire
// and API key belong to the connection, and the options are that connection's
// `embedding`-modality models. Changing the model or its dimensions re-embeds
// every store, so a confirmation guards it.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  EmbeddingChunkingFields,
  EmbeddingModelFields,
} from "@/components/settings/EmbeddingPanels";
import { ApiError, translateApiError } from "@/lib/api/errors";
import {
  useEmbeddingConfig,
  useEmbeddingModels,
  useUpdateEmbeddingConfig,
  type EmbeddingConfigUpdate,
} from "@/lib/hooks/useEmbeddingConfig";
import { useTestEmbedding } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";

export function EmbeddingSettings() {
  const { t } = useTranslation();
  const { data, isPending, error } = useEmbeddingConfig();
  const update = useUpdateEmbeddingConfig();
  const { data: providers = [] } = useProviders();
  const test = useTestEmbedding();

  const [enabled, setEnabled] = useState(false);
  const [connection, setConnection] = useState("");
  const [model, setModel] = useState("");
  const [dimensions, setDimensions] = useState(768);
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(64);
  // Holds the pending change while the re-embed confirmation is shown.
  const [confirm, setConfirm] = useState<Partial<EmbeddingConfigUpdate> | null>(null);

  // Seed the form from the loaded config once it arrives.
  useEffect(() => {
    if (!data) return;
    setEnabled(data.enabled);
    setConnection(data.connection ?? "");
    setModel(data.model ?? "");
    setDimensions(data.dimensions);
    setChunkSize(data.default_chunk_size);
    setChunkOverlap(data.default_chunk_overlap);
  }, [data]);

  const picked = providers.find((p) => p.name === connection) ?? null;
  const { options } = useEmbeddingModels(picked);
  // Keep the saved model selectable even when the connection cannot list it
  // (the endpoint stopped serving it, or the probe failed) — the same courtesy
  // the internal-engine picker does its own saved model.
  const modelOptions = model && !options.includes(model) ? [model, ...options] : options;

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

  // PUT the full config from state, `override` winning — an auto-save passes
  // its just-changed field that way (state cannot be read back synchronously).
  const persist = (override: Partial<EmbeddingConfigUpdate> = {}) =>
    update.mutate({
      enabled,
      connection: connection || null,
      model: model.trim() || null,
      dimensions,
      default_chunk_size: chunkSize,
      default_chunk_overlap: chunkOverlap,
      ...override,
    });

  // Changing the model or the vector width of an ALREADY configured embedder
  // re-embeds every store (a width change rebuilds the vec table), so confirm
  // first; first-time configuration commits directly.
  const configured = (data?.model ?? "") !== "";
  const save = (override: Partial<EmbeddingConfigUpdate>) =>
    configured ? setConfirm(override) : persist(override);

  // Backing out of the confirmation must also back out of the staged edit, or
  // the fields would keep showing a model the daemon was never told about.
  const cancelConfirm = () => {
    setConfirm(null);
    setConnection(data?.connection ?? "");
    setModel(data?.model ?? "");
    setDimensions(data?.dimensions ?? dimensions);
  };

  // A model belongs to the connection it came from, so switching connections
  // clears it — and nothing is written until a model is picked, because a config
  // naming a connection and no model is one the daemon refuses.
  const pickConnection = (name: string) => {
    setConnection(name);
    setModel("");
    test.reset();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.embedding.title")}</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">{t("settings.embedding.description")}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <EmbeddingModelFields
          connections={providers.map((p) => p.name)}
          connection={connection}
          onConnectionChange={pickConnection}
          model={model}
          onModelChange={(m) => {
            setModel(m);
            test.reset();
            save({ connection: connection || null, model: m });
          }}
          modelOptions={modelOptions}
          modelsHint={
            picked && options.length === 0 ? t("settings.embedding.noEmbeddingModels") : undefined
          }
          dimensions={dimensions}
          onDimensionsChange={setDimensions}
          onDimensionsCommit={() => {
            if (dimensions !== data?.dimensions) save({ dimensions });
          }}
          notConfigured={!configured}
          onTest={() => test.mutate({ connection, model })}
          testPending={test.isPending}
          testResult={test.data ?? null}
          disabled={update.isPending}
        />

        <EmbeddingChunkingFields
          enabled={enabled}
          onEnabledChange={(v) => {
            setEnabled(v);
            persist({ enabled: v });
          }}
          chunkSize={chunkSize}
          onChunkSizeChange={setChunkSize}
          onChunkSizeCommit={() => {
            if (chunkSize !== data?.default_chunk_size) persist({ default_chunk_size: chunkSize });
          }}
          chunkOverlap={chunkOverlap}
          onChunkOverlapChange={setChunkOverlap}
          onChunkOverlapCommit={() => {
            if (chunkOverlap !== data?.default_chunk_overlap)
              persist({ default_chunk_overlap: chunkOverlap });
          }}
          disabled={update.isPending}
        />

        {/* A rejected selection is a 422 naming exactly what is wrong (unknown
            connection, a wire with no embedding API, a model this connection
            does not offer) — shown beside the fields it is about, and shown
            VERBATIM, since the generic `errors.CONFIG_INVALID` string would
            throw away the half that says which. */}
        {update.error ? (
          <p className="text-sm text-destructive" role="alert">
            {update.error instanceof ApiError && update.error.code === "CONFIG_INVALID"
              ? update.error.envelopeMessage
              : translateApiError(t, update.error)}
          </p>
        ) : null}
      </CardContent>

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && cancelConfirm()}
        title={t("settings.embedding.changeModelTitle")}
        description={t("settings.embedding.changeModelConfirm")}
        confirmLabel={t("settings.embedding.changeModelConfirmLabel")}
        variant="default"
        pending={update.isPending}
        onConfirm={() => {
          if (confirm) persist(confirm);
          setConfirm(null);
        }}
      />
    </Card>
  );
}
