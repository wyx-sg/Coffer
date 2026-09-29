// src/components/providers/ProviderModelsTab.tsx — the Models tab: which of the endpoint's models the provider offers.
//
// The endpoint is introspected when the provider opens — no fetch button (spec
// provider-switching "Introspect the endpoint when the Models tab opens"). One
// row per model: its switch, id, what uses it, and its type (correctable in
// place). Search and a type filter narrow the rows. A probe that fails says so
// with a Retry and leaves the selection alone; an endpoint that lists nothing
// says what that means.
import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Loader2, RefreshCw } from "lucide-react";

import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { SearchInput } from "@/components/SearchInput";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { MODALITIES, type Modality, type Provider } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { probeFailed } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { cn } from "@/lib/utils";
import { ModelsNotice } from "./ModelsNotice";
import { ProviderModelRow } from "./ProviderModelRow";
import { useModelCuration } from "./useModelCuration";

const PAGE = 50;

interface Props {
  provider: Provider;
  use: ProviderUse;
  endpoint: UseQueryResult<EndpointModelsOut>;
  engineModel: string | null;
  transcribeModel: string | null;
}

export function ProviderModelsTab({
  provider,
  use,
  endpoint,
  engineModel,
  transcribeModel,
}: Props) {
  const { t, i18n } = useTranslation();
  const fetched = endpoint.data?.models ?? [];
  const cur = useModelCuration(provider, fetched);
  const [query, setQuery] = useState("");
  const [type, setType] = useState<Modality | "all">("all");
  const [shown, setShown] = useState(PAGE);

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

  const tagsFor = (id: string): string[] => [
    ...use.agents
      .filter(({ model }) => model === id)
      .map(({ agent }) => t("providers.models.agentDefault", { agent: agent.display_name })),
    ...(use.engine && engineModel === id ? [t("providers.usedBy.engine")] : []),
    ...(use.transcribe && transcribeModel === id ? [t("providers.usedBy.transcribe")] : []),
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder={t("providers.models.search")}
          ariaLabel={t("providers.models.search")}
          className="w-56"
        />
        <div role="group" aria-label={t("providers.models.typeFilter")} className="flex gap-1">
          {(["all", ...types] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={type === m}
              onClick={() => setType(m)}
              className={cn(
                "h-7 rounded-md px-2.5 text-xs font-label outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
                type === m
                  ? "bg-surface-selected text-text"
                  : "text-text-muted hover:bg-surface-hover",
              )}
            >
              {m === "all" ? t("providers.models.allTypes") : t(`providers.modalities.${m}`)}
            </button>
          ))}
        </div>
        <span className="ml-auto flex items-center gap-2 text-xs text-text-muted">
          {endpoint.isFetching ? (
            <span role="status" className="inline-flex items-center gap-1.5">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              {t("providers.models.listing")}
            </span>
          ) : endpoint.dataUpdatedAt ? (
            t("providers.models.listedAgo", {
              ago: formatRelativeTime(
                new Date(endpoint.dataUpdatedAt).toISOString(),
                i18n.language,
              ),
            })
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={() => void endpoint.refetch()}
            disabled={endpoint.isFetching}
          >
            <RefreshCw aria-hidden /> {t("providers.models.refresh")}
          </Button>
        </span>
      </div>
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
    </div>
  );
}
