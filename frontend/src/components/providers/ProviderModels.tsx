// src/components/providers/ProviderModels.tsx — the Models section: which of the endpoint's models the provider offers, and what each costs.
//
// The endpoint is introspected when the provider opens — no fetch button (spec
// provider-switching "Introspect the endpoint when the Models tab opens"). One
// row per model: its switch, id, what uses it, its price with where the price
// came from, and its type (correctable in place). Search and a type filter
// narrow the rows. A probe that fails says so with a Retry and leaves the
// selection alone; an endpoint that lists nothing says what that means.
// Prices are refetched after every listing: that is when a provider's own API
// reports them (spec provider-switching "Resolve each model's price from the
// provider, its API, or the bundled list").
import { useMemo, useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { MODALITIES, type Modality, type Provider } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { useModelPrices } from "@/lib/hooks/useProviderFallback";
import { probeFailed } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { ModelPriceCell } from "./ModelPriceCell";
import { ModelsNotice } from "./ModelsNotice";
import { ModelsToolbar } from "./ModelsToolbar";
import { ProviderModelRow } from "./ProviderModelRow";
import { Section } from "@/components/Section";
import { SetPriceDialog } from "./SetPriceDialog";
import { useModelCuration } from "./useModelCuration";

const PAGE = 50;

interface Props {
  provider: Provider;
  use: ProviderUse;
  endpoint: UseQueryResult<EndpointModelsOut>;
  engineModel: string | null;
  transcribeModel: string | null;
}

export function ProviderModels({ provider, use, endpoint, engineModel, transcribeModel }: Props) {
  const { t } = useTranslation();
  const fetched = endpoint.data?.models ?? [];
  const cur = useModelCuration(provider, fetched);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<Modality | "all">("all");
  const [shown, setShown] = useState(PAGE);
  const [pricing, setPricing] = useState<string | null>(null);
  const local = provider.local_runtime != null;

  const ids = useMemo(() => cur.rows.map((m) => m.id), [cur.rows]);
  const prices = useModelPrices(provider.uid, ids, endpoint.dataUpdatedAt);
  const priceOf = (id: string) => prices.data?.find((p) => p.model === id);

  const failed = probeFailed(endpoint.data, endpoint.error);
  const reason = endpoint.error ? translateApiError(t, endpoint.error) : endpoint.data?.message;
  const needle = query.trim().toLowerCase();
  const rows = cur.rows.filter(
    (m) =>
      (type === "all" || cur.modalityOf(m) === type) &&
      (!needle || m.id.toLowerCase().includes(needle)),
  );
  // Video only when something is video: the four the design names are enough otherwise.
  const types = MODALITIES.filter(
    (m) => m !== "video" || cur.rows.some((r) => cur.modalityOf(r) === m),
  );
  const offered = cur.unrestricted ? cur.rows.length : provider.models.length;

  const tagsFor = (id: string): string[] => [
    ...use.agents
      .filter(({ model }) => model === id)
      .map(({ agent }) => t("providers.models.agentDefault", { agent: agent.display_name })),
    ...(use.engine && engineModel === id ? [t("providers.usedBy.engine")] : []),
    ...(use.transcribe && transcribeModel === id ? [t("providers.usedBy.transcribe")] : []),
  ];
  const rowOf = (id: string) => cur.rows.find((m) => m.id === id);

  return (
    <Section
      title={t("providers.overview.models")}
      aside={
        <>
          <HelpTip label={t("providers.prices.helpLabel")}>{t("providers.prices.help")}</HelpTip>
          {cur.rows.length > 0 ? (
            <span className="text-xs text-text-muted">
              {t("providers.models.offeredCount", { n: offered, count: cur.rows.length })}
            </span>
          ) : null}
        </>
      }
    >
      <ModelsToolbar
        query={query}
        onQuery={setQuery}
        types={types}
        type={type}
        onType={setType}
        endpoint={endpoint}
      />
      <p className="text-xs text-text-muted">{t("providers.models.hint")}</p>

      {failed ? (
        <ModelsNotice
          tone="error"
          title={t("providers.models.failedTitle")}
          body={t("providers.models.failedBody", { reason: reason ?? "" })}
          action={t("common.retry")}
          onAction={() => void endpoint.refetch()}
        />
      ) : !endpoint.isPending && cur.rows.length === 0 ? (
        <ModelsNotice
          tone="neutral"
          title={t("providers.models.noneTitle")}
          body={t("providers.models.noneBody")}
          action={t("providers.models.refresh")}
          onAction={() => void endpoint.refetch()}
        />
      ) : null}

      {cur.rows.length > 0 ? (
        <div className="flex flex-col rounded-xl border border-border">
          {rows.length === 0 ? (
            <p className="px-3 py-3 text-sm text-text-muted">{t("providers.models.noMatch")}</p>
          ) : (
            rows
              .slice(0, shown)
              .map((m) => (
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
                      disabled={cur.pending}
                      onEdit={local ? undefined : () => setPricing(m.id)}
                      onReset={() => cur.setPrice(m, null)}
                    />
                  }
                />
              ))
          )}
          {rows.length > shown ? (
            <Button variant="ghost" className="m-1" onClick={() => setShown((n) => n + PAGE)}>
              {t("providers.models.showMore", { count: rows.length - shown })}
            </Button>
          ) : null}
        </div>
      ) : null}

      <SetPriceDialog
        model={pricing}
        current={pricing ? priceOf(pricing) : undefined}
        onClose={() => setPricing(null)}
        onSave={(price) => {
          const row = pricing ? rowOf(pricing) : undefined;
          if (row) cur.setPrice(row, price);
        }}
      />
    </Section>
  );
}
