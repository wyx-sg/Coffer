// pages/settings/InternalEngineSettings.tsx — the internal-engine selection
// (spec 011 amendment 2026-06-22b). Coffer's own LLM engine (memory organizer /
// reorg / distill / `coffer__ask`) runs on whichever connection is picked here
// (endpoint + key) with the model chosen here. Both live apart from the chat
// agents: the connection is the global `internal_default`, the model is a
// separate singleton. Replaces the per-card star toggle that used to set it.
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
import type { Provider } from "@/lib/api/providers";
import { useSetInternalDefaultProvider } from "@/lib/hooks/useProviders";
import { useInternalEngineConfig, useSetInternalEngineModel } from "@/lib/hooks/useInternalEngine";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";

interface Props {
  providers: Provider[];
}

export function InternalEngineSettings({ providers }: Props) {
  const { t } = useTranslation();
  const selected = providers.find((p) => p.internal_default) ?? null;
  const setInternalDefault = useSetInternalDefaultProvider();
  const { data: config } = useInternalEngineConfig();
  const setModel = useSetInternalEngineModel();
  const listModels = useListProviderModels();
  const [models, setModels] = useState<string[]>([]);

  // Fetch the chosen connection's models so the model dropdown is populated.
  useEffect(() => {
    if (!selected) {
      setModels([]);
      return;
    }
    listModels.mutate(
      {
        provider: selected.wire_format,
        base_url: selected.base_url,
        credential_ref: selected.credential_ref,
      },
      { onSuccess: (r) => setModels(r.models) },
    );
    // listModels identity is stable across renders; re-fetch only on connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.name, selected?.base_url, selected?.credential_ref]);

  const currentModel = config?.model ?? "";
  // Show the saved model even when the endpoint can't list it.
  const options = currentModel && !models.includes(currentModel) ? [currentModel, ...models] : models;

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
