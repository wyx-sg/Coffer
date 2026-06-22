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
import { PasswordInput } from "@/components/ui/password-input";
import { ProviderModelField } from "@/components/settings/ProviderModelField";

// Mainstream embedding providers, plus "custom" for any OpenAI-compatible
// endpoint not in the list (the user supplies its own base URL + key).
const PROVIDERS = [
  "openai",
  "voyage",
  "jina",
  "cohere",
  "gemini",
  "mistral",
  "azure",
  "dashscope",
  "ollama",
  "lmstudio",
  "local",
  "custom",
];

// Providers that run locally and need no API key.
const KEYLESS = ["local", "ollama", "lmstudio"];

// A vector's dimension is a fixed property of the embedding model, so when the
// user picks a known model we fill it in and lock the field. Custom / unlisted
// models keep the field editable (some support Matryoshka-style truncation).
const KNOWN_DIMS: Record<string, number> = {
  "text-embedding-3-small": 1536,
  "text-embedding-3-large": 3072,
  "text-embedding-ada-002": 1536,
  "voyage-3": 1024,
  "voyage-3-lite": 512,
  "voyage-3-large": 1024,
  "voyage-code-3": 1024,
  "jina-embeddings-v3": 1024,
  "embed-english-v3.0": 1024,
  "embed-multilingual-v3.0": 1024,
  "text-embedding-004": 768,
  "gemini-embedding-001": 3072,
  "mistral-embed": 1024,
  "text-embedding-v3": 1024,
  "bge-m3": 1024,
  "bge-large-en-v1.5": 1024,
  "nomic-embed-text": 768,
  "mxbai-embed-large": 1024,
  "snowflake-arctic-embed": 1024,
  "all-minilm": 384,
};

/** What the dialog seeds from: the existing config. `credential_ref` is the
 * stored key's vault ref (used to probe in edit mode) — its presence means a key
 * is already saved, so the key field becomes optional ("leave blank to keep"). */
export interface EmbeddingModelInitial {
  provider: string;
  model: string;
  dimensions: number;
  base_url: string | null;
  credential_ref: string | null;
}

/** What the dialog emits: the user types a raw `secret_value` (API key), not a
 * vault ref — the backend stores it. Null = keep the existing stored key. */
export interface EmbeddingModelValues {
  provider: string;
  model: string;
  dimensions: number;
  base_url: string | null;
  secret_value: string | null;
}

interface Props {
  initial: EmbeddingModelInitial;
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
  // The raw key the user types — never seeded (we don't hold the stored key).
  const [secret, setSecret] = useState("");

  // Re-seed when the dialog reopens against a different initial value.
  useEffect(() => {
    setProvider(initial.provider);
    setModel(initial.model);
    setDimensions(initial.dimensions);
    setBaseUrl(initial.base_url ?? "");
    setSecret("");
  }, [initial]);

  const hasStoredKey = initial.credential_ref != null;

  const keyless = KEYLESS.includes(provider);

  // A known model's dimension is fixed — auto-fill it and lock the field; a
  // custom/unlisted model leaves the dimension editable.
  const knownDim = KNOWN_DIMS[model.trim()];
  useEffect(() => {
    if (knownDim !== undefined) setDimensions(knownDim);
  }, [knownDim]);

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
          secret_value: keyless ? null : secret.trim() || null,
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
        credentialRef={initial.credential_ref}
        secretValue={secret.trim() || null}
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
          disabled={knownDim !== undefined}
          onChange={(e) => setDimensions(Number(e.target.value) || 0)}
        />
        {knownDim !== undefined ? (
          <p className="text-xs text-muted-foreground">
            {t("settings.embedding.dimensionsFixed")}
          </p>
        ) : null}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="emb-base">{t("settings.embedding.baseUrl")}</Label>
        <Input id="emb-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
      </div>

      {!keyless && (
        <div className="space-y-1.5">
          <Label htmlFor="emb-secret">{t("settings.embedding.secret")}</Label>
          <PasswordInput
            id="emb-secret"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder={
              hasStoredKey
                ? t("settings.embedding.secretKeepBlank")
                : t("settings.embedding.secretPlaceholder")
            }
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
