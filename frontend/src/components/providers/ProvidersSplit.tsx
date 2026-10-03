// src/components/providers/ProvidersSplit.tsx — the Model providers page: the list pane beside the open provider.
//
// Both routes render this one layout (`/model-providers` and
// `/model-providers/<uid>`), so the list never re-lays out between
// them. With providers but no uid in the address, the first provider opens
// (a replace-navigation, so Back does not bounce). With none, the page is the
// welcome panel. The endpoint probe of the open provider runs here, once, and
// feeds the header's status, the list row's rejected-key line, the Overview
// and the Models tab.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Box, Plus } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
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
import { AddProviderDialog } from "./AddProviderDialog";
import { ProviderDetail } from "./ProviderDetail";
import { ProviderList } from "./ProviderList";
import { ProviderWelcome } from "./ProviderWelcome";
import { probeOf } from "./probe";

const EMPTY_PROBE = { provider: "", base_url: null, secret_ref: null };

export function ProvidersSplit({ uid }: { uid?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const providers = useProviders();
  const agents = useAgents();
  const engine = useInternalEngineConfig();
  const [adding, setAdding] = useState<PresetId | null>(null);

  const list = providers.data ?? [];
  const agentList = agents.data ?? [];
  const usageOf = (p: Provider) => providerUsedBy(p, list, agentList, engine.data);

  const firstUid = list[0]?.uid;
  useEffect(() => {
    if (!uid && firstUid) {
      navigate(`/model-providers/${encodeURIComponent(firstUid)}`, { replace: true });
    }
  }, [uid, firstUid, navigate]);

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
  const rejected = status === "keyRejected" ? (authStatusOf(endpoint.data?.message) ?? "") : null;

  const header = (
    <PageHeader
      title={t("providers.title")}
      subtitle={t("providers.subtitle")}
      actions={
        <Button onClick={() => setAdding("anthropic")}>
          <Plus aria-hidden /> {t("providers.add.open")}
        </Button>
      }
    />
  );

  let body;
  let split = false;
  if (!providers.error && !providers.isPending && list.length === 0) {
    body = (
      <ProviderWelcome
        agents={agentList}
        engineSet={list.some((p) => p.internal_default)}
        onAdd={setAdding}
      />
    );
  } else {
    split = true;
    const missing =
      !!uid && !provider && !detail.isPending && !providers.isPending && !providers.error;
    const gone =
      !detail.error ||
      (detail.error instanceof ApiError && detail.error.code.endsWith("NOT_FOUND"));
    body = (
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
            selectedRejected={rejected}
          />
        }
        detail={
          <div className="px-7 pb-5 pt-5">
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
                engineModel={engine.data?.model ?? null}
                transcribeModel={engine.data?.transcribe_model ?? null}
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

  const dialog = (
    <AddProviderDialog
      preset={adding}
      onClose={() => setAdding(null)}
      onCreated={(p) => navigate(`/model-providers/${encodeURIComponent(p.uid)}`)}
    />
  );
  // The split is a full-bleed workspace whose two panes scroll on their own
  // (like Skills, MCP servers and Channels); the welcome is an ordinary page.
  return split ? (
    <>
      <div className="-mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
        <div className="shrink-0 border-b border-border-subtle px-6 pb-4 pt-5">{header}</div>
        {body}
      </div>
      {dialog}
    </>
  ) : (
    <div className="flex flex-col gap-4">
      {header}
      {body}
      {dialog}
    </div>
  );
}
