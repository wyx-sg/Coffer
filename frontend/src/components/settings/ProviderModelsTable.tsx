// frontend/src/components/settings/ProviderModelsTable.tsx
//
// The "Models" tab of the connection detail page: WHICH of this endpoint's
// models the connection offers, and WHAT KIND each of them is. The endpoint is
// introspected when the tab OPENS — the same /models/list-models probe, now a
// query instead of a button press, because an MCP server's tools are listed the
// moment you look at it and a provider's models are the same kind of thing:
// what the remote side offers, not something the user should have to ask for.
// Flipping a row's Switch, or correcting a row's modality, PATCHes the whole
// selection back as `models`.
//
// EMPTY selection = NO RESTRICTION — every model the endpoint serves is offered.
// A non-empty one narrows every downstream picker to exactly those entries OF
// THE MODALITY it serves (useAgentConnectionDraft takes the `text` ones, the
// global embedding setting the `embedding` ones). That is why the banner above
// the table, not the table itself, is what tells the user where they stand: an
// empty table is not an empty offering.
//
// The MODALITY column is why one connection can serve more than chat: the same
// base URL and key answer for embedding, image, video and speech models, so
// each row says which kind it is (provider-switching FR-029). Introspection
// GUESSES the value from the id and the user corrects it here; the stored answer
// is the truth and is never re-derived.
//
// An endpoint that cannot list its models (empty result, or a failed probe) is
// reported as such and LEAVES the current selection alone: a curated list the
// user built earlier must survive a probe that fails. A failure is never silent
// — it names itself and offers a retry, because an automatic fetch that quietly
// yields nothing is indistinguishable from an endpoint with nothing to offer.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { DataTable, type Column, type FilterDef } from "@/components/DataTable";
import { ModalitySelect } from "@/components/settings/ModalitySelect";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { MODALITIES, type Modality, type Provider, type ProviderModel } from "@/lib/api/providers";
import { useEndpointModels } from "@/lib/hooks/useModelIntrospection";
import { useUpdateProvider } from "@/lib/hooks/useProviders";

export function ProviderModelsTable({ provider }: { provider: Provider }) {
  const { t } = useTranslation();
  const endpoint = useEndpointModels(provider.name, probe(provider));
  const update = useUpdateProvider();

  // A modality picked on a row that is NOT offered yet has nowhere to be stored
  // — the curated set holds only offered entries — so it is held here until the
  // row is switched on, and travels into the curated entry when it is. Curated
  // rows never come here: correcting one of those PATCHes straight away.
  const [pending, setPending] = useState<Record<string, Modality>>({});

  const selected = provider.models ?? [];
  const fetched = endpoint.data?.models ?? [];
  const isSelected = (id: string) => selected.some((m) => m.id === id);
  // The rows: what the endpoint offers, plus anything already curated that it no
  // longer lists (so a stale pick stays visible AND untoggleable-away).
  const rows: ProviderModel[] = [...selected, ...fetched.filter((m) => !isSelected(m.id))];

  // What the row shows: the STORED modality once curated, else the user's
  // un-committed correction, else the value introspection guessed.
  const modalityOf = (row: ProviderModel) =>
    selected.find((m) => m.id === row.id)?.modality ?? pending[row.id] ?? row.modality;

  const write = (models: ProviderModel[]) =>
    update.mutate({ name: provider.name, patch: { models } });

  const toggle = (row: ProviderModel) =>
    write(
      isSelected(row.id)
        ? selected.filter((m) => m.id !== row.id)
        : [...selected, { id: row.id, modality: modalityOf(row) }],
    );

  const setModality = (row: ProviderModel, modality: Modality) => {
    if (!isSelected(row.id)) {
      setPending((p) => ({ ...p, [row.id]: modality }));
      return;
    }
    write(selected.map((m) => (m.id === row.id ? { ...m, modality } : m)));
  };

  const listMsg = endpoint.data?.message;
  const fetchFailed = endpoint.error != null;
  const modalityLabel = (m: Modality) => t(`settings.connections.detail.modalities.${m}`);

  const columns: Column<ProviderModel>[] = [
    {
      key: "model",
      header: t("settings.connections.detail.modelId"),
      cell: (m) => <span className="font-mono text-xs">{m.id}</span>,
    },
    {
      key: "modality",
      header: t("settings.connections.detail.modality"),
      cell: (m) => (
        <ModalitySelect
          value={modalityOf(m)}
          onChange={(v) => setModality(m, v)}
          disabled={update.isPending}
          label={m.id}
        />
      ),
    },
    {
      key: "status",
      header: t("resources.cols.status"),
      className: "text-right",
      cell: (m) => (
        <Switch
          checked={isSelected(m.id)}
          onCheckedChange={() => toggle(m)}
          disabled={update.isPending}
          aria-label={`${t("resources.cols.status")}: ${m.id}`}
        />
      ),
    },
  ];

  const filters: FilterDef<ProviderModel>[] = [
    {
      key: "status",
      label: t("resources.cols.status"),
      allLabel: t("resources.status.all"),
      accessor: (m) => (isSelected(m.id) ? "enabled" : "disabled"),
      options: [
        { value: "enabled", label: t("common.enabled") },
        { value: "disabled", label: t("common.disabled") },
      ],
    },
    {
      key: "modality",
      label: t("settings.connections.detail.modality"),
      allLabel: t("settings.connections.detail.allModalities"),
      accessor: (m) => modalityOf(m),
      options: MODALITIES.map((value) => ({ value, label: modalityLabel(value) })),
    },
  ];

  return (
    <Card className="space-y-3 p-4">
      {/* The hint sits above the table; the tab label already carries the title
          this card used to repeat. The right-hand slot is now a STATUS, not a
          trigger: the probe is in flight, or it failed and can be retried. */}
      <div className="flex flex-row items-start justify-between gap-3">
        <p className="max-w-prose text-sm text-muted-foreground">
          {t("settings.connections.detail.modelsHint")}
        </p>
        {endpoint.isFetching ? (
          <span
            className="flex shrink-0 items-center gap-1.5 text-sm text-muted-foreground"
            role="status"
          >
            <Loader2 className="size-3.5 animate-spin" />
            {t("settings.connections.detail.loadingModels")}
          </span>
        ) : fetchFailed ? (
          <Button size="sm" variant="outline" onClick={() => void endpoint.refetch()}>
            <RefreshCw className="mr-1.5 size-3.5" />
            {t("settings.connections.detail.retryFetch")}
          </Button>
        ) : null}
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
            error: translateApiError(t, endpoint.error),
          })}
        </p>
      ) : listMsg && fetched.length === 0 ? (
        <p className="text-sm text-amber-600">{listMsg}</p>
      ) : null}

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(m) => m.id}
        search={{
          accessor: (m) => m.id,
          placeholder: t("settings.connections.detail.modelSearchPlaceholder"),
        }}
        filters={filters}
        // DataTable takes ONE empty message, so pick the one that is true: the
        // probe is still running; nothing is curated and the endpoint listed
        // nothing; or the rows exist and the search/filter is what hid them.
        emptyMessage={
          endpoint.isPending
            ? t("settings.connections.detail.loadingModels")
            : rows.length === 0
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
