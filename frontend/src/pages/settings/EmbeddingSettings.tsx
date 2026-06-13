// frontend/src/pages/settings/EmbeddingSettings.tsx
//
// The global embedding configuration (Settings → Embedding). Embedding is no
// longer set per knowledge base / memory store; one config here drives vector
// retrieval everywhere. Turning it off (or leaving provider/model blank) makes
// every store fall back to keyword/grep.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { useEmbeddingConfig, useUpdateEmbeddingConfig } from "@/lib/hooks/useEmbeddingConfig";
import { ProviderModelField } from "@/components/settings/ProviderModelField";

const PROVIDERS = [
  "local",
  "openai",
  "openrouter",
  "voyage",
  "jina",
  "gemini",
  "azure",
  "dashscope",
  "ollama",
  "lmstudio",
];

export function EmbeddingSettings() {
  const { t } = useTranslation();
  const { data, isPending, error } = useEmbeddingConfig();
  const update = useUpdateEmbeddingConfig();

  const [enabled, setEnabled] = useState(false);
  const [provider, setProvider] = useState("local");
  const [model, setModel] = useState("");
  const [dimensions, setDimensions] = useState(768);
  const [baseUrl, setBaseUrl] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(64);

  // Seed the form from the loaded config once it arrives.
  useEffect(() => {
    if (!data) return;
    setEnabled(data.enabled);
    setProvider(data.provider ?? "local");
    setModel(data.model ?? "");
    setDimensions(data.dimensions);
    setBaseUrl(data.base_url ?? "");
    setCredentialRef(data.credential_ref ?? "");
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

  const keyless = ["local", "ollama", "lmstudio"].includes(provider);

  const onSave = () => {
    update.mutate({
      enabled,
      provider: provider || null,
      model: model.trim() || null,
      dimensions,
      base_url: baseUrl.trim() || null,
      credential_ref: credentialRef.trim() || null,
      default_chunk_size: chunkSize,
      default_chunk_overlap: chunkOverlap,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.embedding.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("settings.embedding.description")}</p>

        <div className="flex items-center justify-between gap-4 rounded-md border border-border p-3">
          <div>
            <Label>{t("settings.embedding.enabled")}</Label>
            <p className="text-xs text-muted-foreground">{t("settings.embedding.enabledHint")}</p>
          </div>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>

        {enabled ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="emb-provider">{t("settings.embedding.provider")}</Label>
              <select
                id="emb-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            <ProviderModelField
              provider={provider}
              baseUrl={baseUrl.trim() || null}
              credentialRef={credentialRef.trim() || null}
              model={model}
              onModelChange={setModel}
              kind="embedding"
            />
            <div className="space-y-1">
              <Label htmlFor="emb-dims">{t("settings.embedding.dimensions")}</Label>
              <Input
                id="emb-dims"
                type="number"
                value={dimensions}
                onChange={(e) => setDimensions(Number(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="emb-base">{t("settings.embedding.baseUrl")}</Label>
              <Input id="emb-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            </div>
            {!keyless ? (
              <div className="space-y-1 sm:col-span-2">
                <Label htmlFor="emb-cred">{t("settings.embedding.credential")}</Label>
                <Input
                  id="emb-cred"
                  value={credentialRef}
                  onChange={(e) => setCredentialRef(e.target.value)}
                  placeholder={t("settings.embedding.credentialHint")}
                />
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="space-y-3 border-t border-border pt-4">
          <div>
            <Label>{t("settings.embedding.chunkingTitle")}</Label>
            <p className="text-xs text-muted-foreground">{t("settings.embedding.chunkingHint")}</p>
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
          <Button onClick={onSave} disabled={update.isPending}>
            {update.isPending ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
