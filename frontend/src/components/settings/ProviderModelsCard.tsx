// frontend/src/components/settings/ProviderModelsCard.tsx
//
// The point of the connection detail page: WHICH of this endpoint's models the
// connection offers. "Fetch models" introspects the endpoint (the same
// /models/list-models call ProviderModelField uses); ticking a box PATCHes the
// whole selection back as `models`.
//
// EMPTY selection = NO RESTRICTION — every model the endpoint serves is offered.
// A non-empty one narrows the agent's model picker to exactly those ids
// (useAgentConnectionDraft reads it and skips introspection entirely).
//
// An endpoint that cannot list its models (empty result, or a failed probe) is
// reported as such and LEAVES the current selection alone: a curated list the
// user built earlier must survive a later fetch that fails.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useUpdateProvider } from "@/lib/hooks/useProviders";

export function ProviderModelsCard({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  const list = useListProviderModels();
  const update = useUpdateProvider();
  const [fetched, setFetched] = useState<string[]>([]);

  const selected = provider.models ?? [];
  // The checkbox list: what the endpoint offers, plus anything already curated
  // that it no longer lists (so a stale pick stays visible AND untickable-away).
  const rows = [...selected, ...fetched.filter((m) => !selected.includes(m))];

  const write = (models: string[]) => update.mutate({ name: provider.name, patch: { models } });

  const toggle = (model: string) =>
    write(selected.includes(model) ? selected.filter((m) => m !== model) : [...selected, model]);

  const listMsg = list.data?.message;
  const fetchFailed = list.error != null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-base">{t("settings.connections.detail.models")}</CardTitle>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">
            {t("settings.connections.detail.modelsHint")}
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => list.mutate(probe(provider), { onSuccess: (r) => setFetched(r.models) })}
          disabled={list.isPending}
        >
          {list.isPending ? (
            <Loader2 className="mr-1.5 size-3.5 animate-spin" />
          ) : (
            <RefreshCw className="mr-1.5 size-3.5" />
          )}
          {t("settings.models.fetchModels")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="rounded-md border bg-muted/30 px-3 py-2 text-sm text-muted-foreground"
          role="status"
        >
          {selected.length === 0
            ? t("settings.connections.detail.unrestricted")
            : t("settings.connections.detail.restricted", { count: selected.length })}
        </div>

        {fetchFailed ? (
          <p className="text-sm text-destructive">
            {t("settings.connections.detail.fetchFailed", {
              error: translateApiError(t, list.error),
            })}
          </p>
        ) : listMsg && fetched.length === 0 ? (
          <p className="text-sm text-amber-600">{listMsg}</p>
        ) : null}

        {rows.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            {t("settings.connections.detail.noModelsYet")}
          </p>
        ) : (
          <ul className="space-y-1">
            {rows.map((m) => (
              <li key={m}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted/50">
                  <Checkbox
                    checked={selected.includes(m)}
                    disabled={update.isPending}
                    onChange={() => toggle(m)}
                    aria-label={m}
                  />
                  <span className="font-mono text-xs">{m}</span>
                </label>
              </li>
            ))}
          </ul>
        )}

        {selected.length > 0 ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={update.isPending}
            onClick={() => write([])}
            className="text-muted-foreground"
          >
            {t("settings.connections.detail.clearSelection")}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

/** How to CALL this endpoint: its own wire + endpoint + stored key. The secret
 *  itself never leaves the daemon — only its reference is sent. */
function probe(provider: Provider) {
  return {
    provider: provider.protocol,
    base_url: provider.base_url,
    credential_ref: provider.credential_ref,
  };
}
