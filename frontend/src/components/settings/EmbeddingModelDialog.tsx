// components/settings/EmbeddingModelDialog.tsx — add / edit the single global
// embedding model (spec 006). Mirrors the LLM-connection dialog: provider +
// model (with Fetch models / Test connection via ProviderModelField, kind
// "embedding") + dimensions + base URL + credential reference. There is only
// ever ONE embedding model, so this is an add-or-edit form, not a list.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

const KEYLESS = ["local", "ollama", "lmstudio"];

export interface EmbeddingModelValues {
  provider: string;
  model: string;
  dimensions: number;
  base_url: string | null;
  credential_ref: string | null;
}

interface Props {
  initial: EmbeddingModelValues;
  pending: boolean;
  onSubmit: (values: EmbeddingModelValues) => void;
  onCancel: () => void;
}

export function EmbeddingModelDialog({ initial, pending, onSubmit, onCancel }: Props) {
  const { t } = useTranslation();
  const [provider, setProvider] = useState(initial.provider);
  const [model, setModel] = useState(initial.model);
  const [dimensions, setDimensions] = useState(initial.dimensions);
  const [baseUrl, setBaseUrl] = useState(initial.base_url ?? "");
  const [credentialRef, setCredentialRef] = useState(initial.credential_ref ?? "");

  // Re-seed when the dialog reopens against a different initial value.
  useEffect(() => {
    setProvider(initial.provider);
    setModel(initial.model);
    setDimensions(initial.dimensions);
    setBaseUrl(initial.base_url ?? "");
    setCredentialRef(initial.credential_ref ?? "");
  }, [initial]);

  const keyless = KEYLESS.includes(provider);

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          provider: provider || "local",
          model: model.trim(),
          dimensions,
          base_url: baseUrl.trim() || null,
          credential_ref: keyless ? null : credentialRef.trim() || null,
        });
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor="emb-provider">{t("settings.embedding.provider")}</Label>
        <select
          id="emb-provider"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
          className="border-input bg-background h-9 w-full rounded-md border px-2 text-sm"
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
        requiredModel
      />

      <div className="space-y-1.5">
        <Label htmlFor="emb-dims">{t("settings.embedding.dimensions")}</Label>
        <Input
          id="emb-dims"
          type="number"
          value={dimensions}
          onChange={(e) => setDimensions(Number(e.target.value) || 0)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="emb-base">{t("settings.embedding.baseUrl")}</Label>
        <Input id="emb-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
      </div>

      {!keyless && (
        <div className="space-y-1.5">
          <Label htmlFor="emb-cred">{t("settings.embedding.credential")}</Label>
          <Input
            id="emb-cred"
            value={credentialRef}
            onChange={(e) => setCredentialRef(e.target.value)}
            placeholder={t("settings.embedding.credentialHint")}
          />
        </div>
      )}

      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={pending || !model.trim()}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
