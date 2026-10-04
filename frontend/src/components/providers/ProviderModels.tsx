// src/components/providers/ProviderModels.tsx — the Models section: which of the endpoint's models the provider offers, and what each costs.
//
// The endpoint is introspected when the provider opens — no fetch button (spec
// provider-switching "Introspect the endpoint when the Models tab opens"). One
// row per model: its switch, id, what uses it, its price with where the price
// came from, and its type (correctable in place). Search and a type filter
// narrow the rows. A probe that fails says so in the title ("Listing failed ·
// last listed …", Refresh beside it) and in a box, and leaves the selection
// alone; an endpoint that lists nothing says what that means.
// Prices are refetched after every listing: that is when a provider's own API
// reports them (spec provider-switching "Resolve each model's price from the
// provider, its API, or the bundled list").
import { useEffect, useMemo, useRef, useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { MODALITIES, type Modality, type Provider } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { useModelPrices } from "@/lib/hooks/useProviderFallback";
import { formatPriceDate } from "@/lib/providers/priceDate";
import { probeFailed } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { providerPriceSource } from "@/lib/providers/priceSource";
import { ModelPriceCell } from "./ModelPriceCell";
import { ModelsRefresh } from "./ModelsRefresh";
import { ModelsToolbar } from "./ModelsToolbar";
import { ProblemBox } from "./ProblemBox";
import { ProviderModelRow } from "./ProviderModelRow";
import { SetPriceDialog } from "./SetPriceDialog";
import { useModelCuration } from "./useModelCuration";

/** Rows shown before "Show N more". */
const PAGE = 10;

interface Props {
  provider: Provider;
  use: ProviderUse;
  endpoint: UseQueryResult<EndpointModelsOut>;
  engineModel: string | null;
  transcribeModel: string | null;
  /** A model id to find (the Usage tab's "unpriced" link): prefills the search. */
  focusModel?: string | null;
}

export function ProviderModels({
  provider,
  use,
  endpoint,
  engineModel,
  transcribeModel,
  focusModel,
}: Props) {
  const { t, i18n } = useTranslation();
  const fetched = endpoint.data?.models ?? [];
  const cur = useModelCuration(provider, fetched);
  const [query, setQuery] = useState(focusModel ?? "");
  const [type, setType] = useState<Modality | "all">("all");
  const [all, setAll] = useState(false);
  const [pricing, setPricing] = useState<string | null>(null);
  const local = provider.local_runtime != null;

  // Another model to find (Usage's link while this provider is already open).
  useEffect(() => {
    if (focusModel) setQuery(focusModel);
  }, [focusModel]);

  const ids = useMemo(() => cur.rows.map((m) => m.id), [cur.rows]);
  const prices = useModelPrices(provider.uid, ids, endpoint.dataUpdatedAt);
  const priceOf = (id: string) => prices.data?.find((p) => p.model === id);
  const usual = providerPriceSource(prices.data ?? []);

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
    ...(use.engine && engineModel === id ? [t("providers.usedBy.engine")] : []),
    ...(use.transcribe && transcribeModel === id ? [t("providers.usedBy.transcribe")] : []),
  ];
  const rowOf = (id: string) => cur.rows.find((m) => m.id === id);

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
  const offButton = (
    <Button
      variant="outline"
      size="sm"
      disabled={cur.pending || !cur.canSetMany(rows, false)}
      onClick={() => cur.setMany(rows, false)}
    >
      {t("providers.models.turnAllOff")}
    </Button>
  );
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
            <ModelsToolbar
              query={query}
              onQuery={setQuery}
              types={types}
              type={type}
              onType={setType}
              actions={
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={cur.pending || !cur.canSetMany(rows, true)}
                    onClick={() => cur.setMany(rows, true)}
                  >
                    {t("providers.models.turnAllOn")}
                  </Button>
                  {cur.wouldEmpty(rows) ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span tabIndex={0}>{offButton}</span>
                      </TooltipTrigger>
                      <TooltipContent>{t("providers.models.keepOne")}</TooltipContent>
                    </Tooltip>
                  ) : (
                    offButton
                  )}
                </>
              }
            />
            {rows.length === 0 ? (
              <p className="py-3 text-sm text-text-muted">{t("providers.models.noMatch")}</p>
            ) : (
              <div className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border-subtle bg-surface-raised">
                {shown.map((m) => (
                  <ProviderModelRow
                    key={m.id}
                    id={m.id}
                    on={cur.isOn(m.id)}
                    modality={cur.modalityOf(m)}
                    tags={tagsFor(m.id)}
                    disabled={cur.pending}
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
                  />
                ))}
                {rows.length > PAGE ? (
                  <div className="flex items-center gap-2 px-3.5 py-2.5 text-xs text-text-muted">
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
      <SetPriceDialog
        model={pricing}
        current={pricing ? priceOf(pricing) : undefined}
        onClose={() => setPricing(null)}
        onSave={(price) => {
          const row = pricing ? rowOf(pricing) : undefined;
          if (row) cur.setPrice(row, price);
        }}
        onReset={() => {
          const row = pricing ? rowOf(pricing) : undefined;
          if (row) cur.setPrice(row, null);
        }}
      />
    </>
  );
}
