// src/components/providers/ProviderModels.tsx — the Models section: which of the endpoint's models the provider offers, and what each costs.
//
// The endpoint is introspected when the provider opens — no fetch button (spec
// provider-switching "Introspect the endpoint when the Models tab opens"). One
// row per model: its switch, id, what uses it, its price and its context
// window each with where it came from, and its type (correctable in place). Search and a type filter
// narrow the rows. A probe that fails says so in the title ("Listing failed ·
// last listed …", Refresh beside it) and in a box, and leaves the selection
// alone; an endpoint that lists nothing says what that means.
// Prices and windows are refetched after every listing: that is when a
// provider's own API reports them (spec provider-switching "Resolve each
// model's price from the provider, its API, or the bundled list", "Resolve
// each provider model's context window").
import { useEffect, useMemo, useRef, useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { MODALITIES, type Modality, type Provider, type ProviderModel } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { useModelPrices, useModelWindows } from "@/lib/hooks/useProviderPrices";
import { formatPriceDate } from "@/lib/providers/priceDate";
import { probeFailed } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { useTableSelection } from "@/components/DataTableSelection";
import { Section } from "@/components/Section";
import { providerPriceSource } from "@/lib/providers/priceSource";
import { ModelEditDialogs } from "./ModelEditDialogs";
import { ModelPriceCell } from "./ModelPriceCell";
import { ModelWindowCell } from "./ModelWindowCell";
import { ModelsRefresh } from "./ModelsRefresh";
import { ModelsBulkBar } from "./ModelsBulkBar";
import { ModelsTableHead } from "./ModelsTableHead";
import { ModelsToolbar } from "./ModelsToolbar";
import { ProblemBox } from "./ProblemBox";
import { ProviderModelRow } from "./ProviderModelRow";
import { useModelCuration } from "./useModelCuration";

/** Rows shown before "Show N more". */
const PAGE = 10;

interface Props {
  provider: Provider;
  use: ProviderUse;
  endpoint: UseQueryResult<EndpointModelsOut>;
  transcribeModel: string | null;
  /** A model id to find (the Usage tab's "unpriced" link): prefills the search. */
  focusModel?: string | null;
}

export function ProviderModels({ provider, use, endpoint, transcribeModel, focusModel }: Props) {
  const { t, i18n } = useTranslation();
  const fetched = endpoint.data?.models ?? [];
  const cur = useModelCuration(provider, fetched);
  const [query, setQuery] = useState(focusModel ?? "");
  const [type, setType] = useState<Modality | "all">("all");
  const [all, setAll] = useState(false);
  const [pricing, setPricing] = useState<string | null>(null);
  const [sizing, setSizing] = useState<string | null>(null);
  const local = provider.local_runtime != null;

  // Another model to find (Usage's link while this provider is already open).
  useEffect(() => {
    if (focusModel) setQuery(focusModel);
  }, [focusModel]);

  const ids = useMemo(() => cur.rows.map((m) => m.id), [cur.rows]);
  const prices = useModelPrices(provider.uid, ids, endpoint.dataUpdatedAt);
  const priceOf = (id: string) => prices.data?.find((p) => p.model === id);
  const usual = providerPriceSource(prices.data ?? []);
  const windows = useModelWindows(provider.uid, ids, endpoint.dataUpdatedAt);
  const windowOf = (id: string) => windows.data?.find((w) => w.model === id);

  const failed = probeFailed(endpoint.data, endpoint.error);
  // When the listing last worked, in this session: the title says it beside "Listing failed".
  const lastGood = useRef<number | null>(null);
  if (!failed && endpoint.dataUpdatedAt) lastGood.current = endpoint.dataUpdatedAt;
  const reason = endpoint.error ? translateApiError(t, endpoint.error) : endpoint.data?.message;
  const needle = query.trim().toLowerCase();
  const rows = cur.rows.filter(
    (m) =>
      (type === "all" || cur.modalityOf(m) === type) &&
      (!needle || m.id.toLowerCase().includes(needle)),
  );
  const empty = !endpoint.isPending && !failed && cur.rows.length === 0;
  // Video only when something is video: the four the design names are enough otherwise.
  const types = MODALITIES.filter(
    (m) => m !== "video" || cur.rows.some((r) => cur.modalityOf(r) === m),
  );

  const tagsFor = (id: string): string[] => [
    ...use.agents
      .filter(({ model }) => model === id)
      .map(({ agent }) => t("providers.models.agentDefault", { agent: agent.display_name })),
    ...(use.transcribe && transcribeModel === id ? [t("providers.usedBy.transcribe")] : []),
  ];

  // The one line that says where prices come from; a row says only when it differs.
  const sourceLine =
    usual === null
      ? null
      : usual.source === "provider"
        ? t("providers.models.priceFromProvider", {
            name: usual.name ?? provider.name,
            when: endpoint.dataUpdatedAt
              ? formatRelativeTime(new Date(endpoint.dataUpdatedAt).toISOString(), i18n.language)
              : "",
          })
        : t("providers.models.priceBundled", {
            date: formatPriceDate(usual.updated, i18n.language) ?? "",
          });
  const priceLine = local ? t("providers.models.priceLocal") : sourceLine;
  const rowKey = (m: ProviderModel) => m.id;
  const selection = useTableSelection(rows, rowKey);
  const picked = selection.selectedRows;
  const allOn = rows.length > 0 && picked.length === rows.length;
  const bulkSet = (on: boolean) => {
    cur.setMany(picked, on);
    selection.clear();
  };
  const shown = all ? rows : rows.slice(0, PAGE);

  return (
    <>
      <Section
        title={t("providers.overview.models")}
        gap="tight"
        help={t("providers.models.help")}
        actions={
          <ModelsRefresh endpoint={endpoint} failed={failed} lastListedAt={lastGood.current} />
        }
      >
        {!empty && priceLine ? <p className="text-xs text-text-muted">{priceLine}</p> : null}
        {failed ? (
          <ProblemBox
            tone="error"
            title={t("providers.models.failedTitle")}
            body={t("providers.models.failedBody", { reason: reason ?? "" })}
          />
        ) : empty ? (
          <ProblemBox
            tone="neutral"
            title={t("providers.models.noneTitle")}
            body={t("providers.models.noneBody")}
          />
        ) : null}
        {cur.rows.length > 0 ? (
          <div className="mt-1 flex flex-col gap-2.5">
            {picked.length > 0 ? (
              <ModelsBulkBar
                count={picked.length}
                total={rows.length}
                onClear={selection.clear}
                busy={cur.pending}
                offCount={picked.filter((m) => !cur.isOn(m.id)).length}
                onCount={picked.filter((m) => cur.isOn(m.id)).length}
                onSet={bulkSet}
              />
            ) : (
              <ModelsToolbar
                query={query}
                onQuery={setQuery}
                types={types}
                type={type}
                onType={setType}
              />
            )}
            {rows.length === 0 ? (
              <p className="py-3 text-sm text-text-muted">{t("providers.models.noMatch")}</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised">
                <table className="w-full table-fixed border-collapse text-left">
                  <ModelsTableHead
                    allOn={allOn}
                    someOn={picked.length > 0 && !allOn}
                    onToggleAll={() => selection.setMany(rows.map(rowKey), !allOn)}
                  />
                  <tbody>
                    {shown.map((m) => (
                      <ProviderModelRow
                        key={m.id}
                        id={m.id}
                        on={cur.isOn(m.id)}
                        modality={cur.modalityOf(m)}
                        tags={tagsFor(m.id)}
                        disabled={cur.pending}
                        selected={selection.keys.has(m.id)}
                        onSelect={() => selection.toggle(m.id)}
                        onToggle={() => cur.toggle(m)}
                        onModality={(v) => cur.setModality(m, v)}
                        price={
                          <ModelPriceCell
                            id={m.id}
                            price={priceOf(m.id)}
                            usual={usual?.source ?? null}
                            disabled={cur.pending}
                            onEdit={local ? undefined : () => setPricing(m.id)}
                          />
                        }
                        window={
                          <ModelWindowCell
                            id={m.id}
                            window={windowOf(m.id)}
                            disabled={cur.pending}
                            onEdit={() => setSizing(m.id)}
                          />
                        }
                      />
                    ))}
                  </tbody>
                </table>
                {rows.length > PAGE ? (
                  <div className="flex items-center gap-2 border-t border-border-subtle px-4 py-2.5 text-xs text-text-muted">
                    {t("providers.models.showing", { shown: shown.length, total: rows.length })}
                    {all ? null : (
                      <button
                        type="button"
                        className="font-label text-accent-text outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring"
                        onClick={() => setAll(true)}
                      >
                        {t("providers.models.showMore", { count: rows.length - PAGE })}
                      </button>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </Section>
      <ModelEditDialogs
        cur={cur}
        pricing={pricing}
        sizing={sizing}
        price={pricing ? priceOf(pricing) : undefined}
        window={sizing ? windowOf(sizing) : undefined}
        onClose={() => (setPricing(null), setSizing(null))}
      />
    </>
  );
}
