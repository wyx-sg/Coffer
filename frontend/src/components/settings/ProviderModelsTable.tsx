// frontend/src/components/settings/ProviderModelsTable.tsx
//
// The "Models" tab of the connection detail page: WHICH of this endpoint's
// models the connection offers. "Fetch models" introspects the endpoint (the
// same /models/list-models call ProviderModelField uses); flipping a row's
// Switch PATCHes the whole selection back as `models`.
//
// EMPTY selection = NO RESTRICTION — every model the endpoint serves is offered.
// A non-empty one narrows the agent's model picker to exactly those ids
// (useAgentConnectionDraft reads it and skips introspection entirely). That is
// why the banner above the table, not the table itself, is what tells the user
// where they stand: an empty table is not an empty offering.
//
// An endpoint that cannot list its models (empty result, or a failed probe) is
// reported as such and LEAVES the current selection alone: a curated list the
// user built earlier must survive a later fetch that fails.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useUpdateProvider } from "@/lib/hooks/useProviders";

export function ProviderModelsTable({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  const list = useListProviderModels();
  const update = useUpdateProvider();
  const [fetched, setFetched] = useState<string[]>([]);

  const selected = provider.models ?? [];
  // The rows: what the endpoint offers, plus anything already curated that it no
  // longer lists (so a stale pick stays visible AND untoggleable-away).
  const rows = [...selected, ...fetched.filter((m) => !selected.includes(m))];

  const write = (models: string[]) => update.mutate({ name: provider.name, patch: { models } });

  const toggle = (model: string) =>
    write(selected.includes(model) ? selected.filter((m) => m !== model) : [...selected, model]);

  const listMsg = list.data?.message;
  const fetchFailed = list.error != null;

  const columns: Column<string>[] = [
    {
      key: "model",
      header: t("settings.connections.detail.modelId"),
      cell: (m) => <span className="font-mono text-xs">{m}</span>,
    },
    {
      key: "status",
      header: t("resources.cols.status"),
      className: "text-right",
      cell: (m) => (
        <Switch
          checked={selected.includes(m)}
          onCheckedChange={() => toggle(m)}
          disabled={update.isPending}
          aria-label={`${t("resources.cols.status")}: ${m}`}
        />
      ),
    },
  ];

  const filters: FilterDef<string>[] = [
    {
      key: "status",
      label: t("resources.cols.status"),
      allLabel: t("resources.status.all"),
      accessor: (m) => (selected.includes(m) ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
  ];

  return (
    <Card className="space-y-3 p-4">
      {/* The hint and the fetch trigger sit above the table; the tab label
          already carries the title this card used to repeat. */}
      <div className="flex flex-row items-start justify-between gap-3">
        <p className="max-w-prose text-sm text-muted-foreground">
          {t("settings.connections.detail.modelsHint")}
        </p>
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
      </div>

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

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(m) => m}
        search={{
          accessor: (m) => m,
          placeholder: t("settings.connections.detail.modelSearchPlaceholder"),
        }}
        filters={filters}
        // DataTable takes ONE empty message, so pick the one that is true: with
        // nothing curated and nothing fetched there is nothing to find yet;
        // otherwise the rows exist and the search/filter is what hid them.
        emptyMessage={
          rows.length === 0
            ? t("settings.connections.detail.noModelsYet")
            : t("settings.connections.detail.noModelsMatch")
        }
      />

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
