// src/components/providers/ProvidersSplit.tsx — the Model providers page: the list pane beside the open provider.
//
// Both routes render this one layout (`/model-providers` and
// `/model-providers/<uid>`), so the list never re-lays out between
// them. With providers but no uid in the address, the first provider opens
// (a replace-navigation, so Back does not bounce); `?provider=<uid>` (the
// Usage tab's "unpriced" link) opens that one instead, and `?model=<id>` is
// handed to the Models search. With none, the page is the first-run state.
// The page header, tabs and Add dialog belong to ModelProvidersPage. The endpoint probe of the open provider runs here, once, and
// feeds the header's status, the list row's rejected-key line, the Overview
// and the Models tab.
import { useEffect } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Box } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { SplitView } from "@/components/SplitView";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { Provider } from "@/lib/api/providers";
import { useAgents } from "@/lib/hooks/useAgents";
import { useInternalEngineConfig } from "@/lib/hooks/useInternalEngine";
import { useEndpointModels } from "@/lib/hooks/useModelIntrospection";
import { useProvider, useProviders } from "@/lib/hooks/useProviders";
import type { PresetId } from "@/lib/providers/presets";
import { authStatusOf, probeStatus } from "@/lib/providers/probeStatus";
import { providerUsedBy } from "@/lib/providers/usedBy";
import { useProbeLatency } from "./useProbeLatency";
import { ProviderDetail } from "./ProviderDetail";
import { ProviderList } from "./ProviderList";
import { ProviderWelcome } from "./ProviderWelcome";
import { probeOf } from "./probe";

const EMPTY_PROBE = { provider: "", base_url: null, secret_ref: null };

export function ProvidersSplit({
  uid,
  onAdd,
}: {
  uid?: string;
  onAdd: (preset: PresetId) => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const providers = useProviders();
  const agents = useAgents();
  const engine = useInternalEngineConfig();

  const list = providers.data ?? [];
  const agentList = agents.data ?? [];
  const usageOf = (p: Provider) => providerUsedBy(p, list, agentList, engine.data);

  // `?provider=` names the provider to open; without a uid the first one opens.
  const wanted = uid ? undefined : (params.get("provider") ?? undefined);
  const target = wanted && list.some((p) => p.uid === wanted) ? wanted : list[0]?.uid;
  const model = params.get("model");
  useEffect(() => {
    if (!uid && target) {
      const query = wanted && model ? `?model=${encodeURIComponent(model)}` : "";
      navigate(`/model-providers/${encodeURIComponent(target)}${query}`, { replace: true });
    }
  }, [uid, target, wanted, model, navigate]);

  const detail = useProvider(uid ?? "");
  const provider = detail.data ?? list.find((p) => p.uid === uid);
  const endpoint = useEndpointModels(
    provider?.uid ?? "",
    provider ? probeOf(provider) : EMPTY_PROBE,
  );
  const status = probeStatus({
    data: endpoint.data,
    error: endpoint.error,
    pending: endpoint.isPending || endpoint.isFetching,
  });
  const latency = useProbeLatency(provider?.uid, endpoint);
  const rejected = status === "keyRejected" ? (authStatusOf(endpoint.data?.message) ?? "") : null;
  const unreachable = status === "unreachable" ? "unreachable" : null;

  if (!providers.error && !providers.isPending && list.length === 0) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ProviderWelcome onAdd={onAdd} />
      </div>
    );
  }

  const missing =
    !!uid && !provider && !detail.isPending && !providers.isPending && !providers.error;
  const gone =
    !detail.error || (detail.error instanceof ApiError && detail.error.code.endsWith("NOT_FOUND"));
  return (
    <SplitView
      storageKey="providers.list"
      defaultListWidth={292}
      label={t("splitView.resizeList")}
      className="min-h-0 flex-1"
      listClassName="overflow-y-auto"
      detailClassName="overflow-y-auto"
      list={
        <ProviderList
          providers={list}
          isLoading={providers.isPending}
          error={providers.error}
          onRetry={() => void providers.refetch()}
          selectedUid={uid}
          usageOf={usageOf}
          selectedProblem={rejected !== null ? "keyRejected" : unreachable}
        />
      }
      detail={
        <div className="px-8 pb-8 pt-5">
          {providers.error || providers.isPending ? null : missing && gone && uid ? (
            <DetailNotFound kind="providers" id={uid} backTo="/model-providers" icon={Box} />
          ) : missing ? (
            <EmptyState
              icon={Box}
              tone={detail.error ? "error" : "default"}
              title={t("providers.detail.notFound")}
              description={detail.error ? translateApiError(t, detail.error) : undefined}
              action={
                <Button asChild variant="outline">
                  <Link to="/model-providers">
                    <ArrowLeft aria-hidden /> {t("providers.detail.backToList")}
                  </Link>
                </Button>
              }
            />
          ) : provider ? (
            <ProviderDetail
              provider={provider}
              use={usageOf(provider)}
              endpoint={endpoint}
              status={status}
              latencyMs={latency}
              engineModel={engine.data?.model ?? null}
              transcribeModel={engine.data?.transcribe_model ?? null}
              focusModel={uid ? model : null}
            />
          ) : (
            <div className="flex flex-col gap-4" aria-busy="true">
              <Skeleton className="h-8 w-64" />
              <Skeleton className="h-40 w-full" />
            </div>
          )}
        </div>
      }
    />
  );
}
