// components/settings/ProviderModelField.tsx
//
// Reusable model field shared by the LLM model form and the embedding config:
// an editable combobox (free text + a datalist of fetched models), a "Fetch
// models" button that pulls the provider's models, and a "Test connection"
// button that probes the provider. Always lets the user type a model id
// manually — the dropdown is assistive, and a provider that can't list models
// just yields an empty list + message.
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Loader2, RefreshCw, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useListProviderModels,
  useTestConnection,
  useTestEmbedding,
} from "@/lib/hooks/useModelIntrospection";

interface Props {
  provider: string;
  baseUrl: string | null;
  credentialRef: string | null;
  /** Inline, not-yet-saved key so test/fetch works before the connection is
   * saved; takes precedence over credentialRef server-side. */
  secretValue?: string | null;
  model: string;
  onModelChange: (value: string) => void;
  kind: "chat" | "embedding";
  /** Mark the model input as required (create mode); edit mode leaves it optional. */
  requiredModel?: boolean;
}

export function ProviderModelField({
  provider,
  baseUrl,
  credentialRef,
  secretValue,
  model,
  onModelChange,
  kind,
  requiredModel,
}: Props) {
  const { t } = useTranslation();
  const listId = useId();
  const [fetched, setFetched] = useState<string[]>([]);

  const list = useListProviderModels();
  const testChat = useTestConnection();
  const testEmbedding = useTestEmbedding();
  const test = kind === "embedding" ? testEmbedding : testChat;

  const probe = {
    provider,
    base_url: baseUrl,
    credential_ref: credentialRef,
    secret_value: secretValue ?? null,
  };

  const onFetch = () => list.mutate(probe, { onSuccess: (r) => setFetched(r.models) });

  const onTest = () => test.mutate({ ...probe, model });

  const listMsg = list.data?.message;
  const result = test.data;

  return (
    <div className="grid gap-1.5">
      <div className="flex items-center justify-between">
        <Label htmlFor="model">{t("settings.models.modelId")}</Label>
        <button
          type="button"
          onClick={onFetch}
          disabled={list.isPending}
          className="flex items-center gap-1 text-xs text-primary hover:underline disabled:opacity-50"
        >
          {list.isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <RefreshCw className="size-3" />
          )}
          {t("settings.models.fetchModels")}
        </button>
      </div>
      <Input
        id="model"
        list={listId}
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
        placeholder={t("settings.models.modelIdPlaceholder")}
        required={requiredModel}
      />
      <datalist id={listId}>
        {fetched.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>

      {listMsg && fetched.length === 0 && <p className="text-xs text-amber-600">{listMsg}</p>}
      {fetched.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {t("settings.models.fetchedCount", { count: fetched.length })}
        </p>
      )}

      <div className="flex items-center gap-2 pt-1">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={onTest}
          disabled={test.isPending || !model}
        >
          {test.isPending && <Loader2 className="mr-1 size-3.5 animate-spin" />}
          {t("settings.models.testConnection")}
        </Button>
        {result && (
          <span
            className={`flex items-center gap-1 text-xs ${result.ok ? "text-green-600" : "text-destructive"}`}
            role="status"
          >
            {result.ok ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
            {result.message}
          </span>
        )}
      </div>
    </div>
  );
}
