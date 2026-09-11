// pages/settings/InternalEngineSettings.tsx — the internal-engine selection
// (spec provider-switching amendment 2026-06-22b). Coffer's own LLM engine — the notes tidy
// pass, and whatever else Coffer runs itself — uses whichever connection is picked here
// (endpoint + key) with the model chosen here. Both live apart from the chat
// agents: the connection is the global `internal_default`, the model is a
// separate singleton. Replaces the per-card star toggle that used to set it.
//
// It is Coffer's own configuration, not a resource served to agents, so it sits
// under Settings → Engine and reads the connection list itself rather than
// taking it from a resource page above.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Cpu } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useProviders, useSetInternalDefaultProvider } from "@/lib/hooks/useProviders";
import { useInternalEngineConfig, useSetInternalEngineModel } from "@/lib/hooks/useInternalEngine";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";

export function InternalEngineSettings() {
  const { t } = useTranslation();
  const { data: providers = [], isPending, error } = useProviders();
  const selected = providers.find((p) => p.internal_default) ?? null;
  const setInternalDefault = useSetInternalDefaultProvider();
  const { data: config } = useInternalEngineConfig();
  const setModel = useSetInternalEngineModel();
  const listModels = useListProviderModels();
  const [models, setModels] = useState<string[]>([]);

  // Fetch the chosen connection's models so the model dropdown is populated.
  // `stale` guards against a slower earlier request landing after a newer one
  // when the connection is switched rapidly.
  useEffect(() => {
    if (!selected) {
      setModels([]);
      return;
    }
    let stale = false;
    listModels.mutate(
      {
        provider: selected.protocol,
        base_url: selected.base_url,
        credential_ref: selected.credential_ref,
      },
      {
        onSuccess: (r) => {
          if (!stale) setModels(r.models);
        },
      },
    );
    return () => {
      stale = true;
    };
    // listModels identity is stable across renders; re-fetch only on connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.name, selected?.base_url, selected?.credential_ref]);

  const currentModel = config?.model ?? "";
  // Show the saved model even when the endpoint can't list it.
  const options =
    currentModel && !models.includes(currentModel) ? [currentModel, ...models] : models;

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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="size-5 text-primary" strokeWidth={1.5} />
          {t("settings.internalEngine.title")}
        </CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("settings.internalEngine.subtitle")}
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>{t("settings.internalEngine.connection")}</Label>
          <Select
            value={selected?.name ?? ""}
            onValueChange={(name) => setInternalDefault.mutate(name)}
            disabled={providers.length === 0 || setInternalDefault.isPending}
          >
            <SelectTrigger aria-label={t("settings.internalEngine.connection")}>
              <SelectValue placeholder={t("settings.internalEngine.connectionPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label>{t("settings.internalEngine.model")}</Label>
          <Select
            value={currentModel}
            onValueChange={(m) => setModel.mutate(m)}
            disabled={!selected || setModel.isPending}
          >
            <SelectTrigger aria-label={t("settings.internalEngine.model")}>
              <SelectValue placeholder={t("settings.internalEngine.modelPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {options.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
