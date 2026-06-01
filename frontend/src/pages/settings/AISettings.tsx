// frontend/src/pages/settings/AISettings.tsx — Settings → AI (spec 008).
// Configure the built-in agent's LLM provider GLOBALLY: per-provider API keys
// (stored write-only in the OS keychain under `ai/<provider>`) plus the
// provider-qualified model. Saving the model ALSO patches the DEFAULT built-in
// agent (`coffer`) so its `model` + `credential_ref` reflect the global config.
//
// Secrets are write-only — the keychain has no read-back. We infer whether a
// provider key is "configured" from the default agent's `credential_ref`
// (which points at `ai/<provider>`) plus any key we just saved this session.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import {
  AI_PROVIDERS,
  DEFAULT_BUILTIN_AGENT,
  MODEL_PRESETS,
  credentialRefFor,
  providerFromModel,
} from "@/lib/aiProviders";
import { useBuiltinAgent, usePatchBuiltinAgent } from "@/lib/hooks/useBuiltinAgents";
import { useRemoveKeychainSecret, useSetKeychainSecret } from "@/lib/hooks/useKeychain";

/** One provider's API-key row: a masked input, a save action, and a status. */
function ProviderKeyRow({
  providerId,
  label,
  configured,
  onSaved,
  onCleared,
}: {
  providerId: string;
  label: string;
  configured: boolean;
  onSaved: () => void;
  onCleared: () => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const ref = credentialRefFor(providerId);
  const setSecret = useSetKeychainSecret();
  const removeSecret = useRemoveKeychainSecret();
  const [value, setValue] = useState("");

  const save = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSecret.mutate(
      { ref, value: trimmed },
      {
        onSuccess: () => {
          setValue("");
          onSaved();
          toast.success(t("settings.ai.keySaved", { provider: label }));
        },
        onError: (err) => toast.error(translateApiError(t, err)),
      },
    );
  };

  const clear = () => {
    removeSecret.mutate(ref, {
      onSuccess: () => {
        onCleared();
        toast.success(t("settings.ai.keyCleared", { provider: label }));
      },
      onError: (err) => toast.error(translateApiError(t, err)),
    });
  };

  const pending = setSecret.isPending || removeSecret.isPending;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{label}</p>
        {configured ? (
          <span className="inline-flex items-center gap-1 text-xs text-primary">
            <Check className="size-3.5" /> {t("settings.ai.configured")}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">{t("settings.ai.notConfigured")}</span>
        )}
      </div>
      <div className="flex gap-2">
        <Input
          type="password"
          autoComplete="off"
          value={value}
          placeholder={
            configured ? t("settings.ai.keyPlaceholderSet") : t("settings.ai.keyPlaceholder")
          }
          aria-label={t("settings.ai.keyLabel", { provider: label })}
          onChange={(e) => setValue(e.target.value)}
        />
        <Button onClick={save} disabled={pending || !value.trim()}>
          {setSecret.isPending ? t("common.saving") : t("settings.ai.saveKey")}
        </Button>
        {configured ? (
          <Button
            variant="outline"
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            onClick={clear}
            disabled={pending}
            aria-label={t("settings.ai.clearKeyAria", { provider: label })}
          >
            <Trash2 className="size-3.5" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function AISettings() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const agent = useBuiltinAgent(DEFAULT_BUILTIN_AGENT);
  const patch = usePatchBuiltinAgent();

  const [model, setModel] = useState("");
  // Providers whose key we saved/cleared this session (the keychain can't be
  // read back, so we layer session edits over the agent-derived baseline).
  const [savedKeys, setSavedKeys] = useState<Record<string, boolean>>({});

  // Seed the model field once the default agent loads.
  useEffect(() => {
    if (agent.data?.config.model) setModel(agent.data.config.model);
  }, [agent.data?.config.model]);

  // A provider is "configured" if the default agent already points its
  // credential_ref at it, OR we saved/cleared its key this session.
  const configuredProvider = useMemo(
    () => providerFromModel(agent.data?.config.credential_ref?.replace(/^ai\//, "") ?? ""),
    [agent.data?.config.credential_ref],
  );
  const isConfigured = (providerId: string): boolean => {
    if (providerId in savedKeys) return savedKeys[providerId];
    return configuredProvider === providerId;
  };

  const saveModel = () => {
    const trimmed = model.trim();
    if (!agent.data || !trimmed) return;
    const provider = providerFromModel(trimmed);
    // Merge over the existing config — the backend forbids extras, so we must
    // send the full valid object.
    patch.mutate(
      {
        name: DEFAULT_BUILTIN_AGENT,
        config: {
          ...agent.data.config,
          model: trimmed,
          credential_ref: credentialRefFor(provider),
        },
      },
      {
        onSuccess: () => toast.success(t("settings.ai.modelSaved")),
        onError: (err) => toast.error(translateApiError(t, err)),
      },
    );
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t("settings.ai.providersTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <p className="text-sm text-muted-foreground">{t("settings.ai.providersHelp")}</p>
          {AI_PROVIDERS.map((p) =>
            p.needsKey ? (
              <ProviderKeyRow
                key={p.id}
                providerId={p.id}
                label={p.label}
                configured={isConfigured(p.id)}
                onSaved={() => setSavedKeys((prev) => ({ ...prev, [p.id]: true }))}
                onCleared={() => setSavedKeys((prev) => ({ ...prev, [p.id]: false }))}
              />
            ) : (
              <div key={p.id} className="flex items-center justify-between">
                <p className="text-sm font-medium">{p.label}</p>
                <span className="text-xs text-muted-foreground">
                  {t("settings.ai.noKeyNeeded")}
                </span>
              </div>
            ),
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("settings.ai.modelTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">{t("settings.ai.modelHelp")}</p>
          {agent.isPending ? (
            <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
          ) : agent.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, agent.error)}</p>
          ) : (
            <>
              <div className="flex gap-2">
                <Input
                  className="font-mono"
                  value={model}
                  list="ai-model-presets"
                  placeholder={t("settings.ai.modelPlaceholder")}
                  aria-label={t("settings.ai.modelLabel")}
                  onChange={(e) => setModel(e.target.value)}
                />
                <datalist id="ai-model-presets">
                  {MODEL_PRESETS.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <Button onClick={saveModel} disabled={patch.isPending || !model.trim()}>
                  {patch.isPending ? t("common.saving") : t("common.save")}
                </Button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {MODEL_PRESETS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    className="rounded-md border px-2 py-1 font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                    onClick={() => setModel(m)}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
