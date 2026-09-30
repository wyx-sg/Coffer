// src/components/providers/ProviderDetail.tsx — the open provider: header, the key-rejected banner, Overview | Models.
//
// The tab lives in the path (`/model-providers/<uid>` for Overview,
// `/model-providers/<uid>/models`) through useDetailTab, so a refresh or a
// deep link lands on it. The dialogs the header and the Overview open —
// Edit, Replace key, Delete — are owned here, once.
import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "@/components/ui/toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Provider } from "@/lib/api/providers";
import { useDetailTab } from "@/lib/detailTabs";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { authStatusOf, probeStatus, type ProbeStatus } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { DeleteProviderDialog } from "./DeleteProviderDialog";
import { EditProviderDialog } from "./EditProviderDialog";
import { KeyRejectedBanner } from "./KeyRejectedBanner";
import { ProviderDetailHeader } from "./ProviderDetailHeader";
import { ProviderModelsTab } from "./ProviderModelsTab";
import { ProviderOverview } from "./ProviderOverview";
import { ReplaceKeyDialog } from "./ReplaceKeyDialog";

const TABS = ["overview", "models"] as const;

interface Props {
  provider: Provider;
  use: ProviderUse;
  endpoint: UseQueryResult<EndpointModelsOut>;
  status: ProbeStatus;
  engineModel: string | null;
  transcribeModel: string | null;
}

type Open = "edit" | "replace" | "delete" | null;

export function ProviderDetail({
  provider,
  use,
  endpoint,
  status,
  engineModel,
  transcribeModel,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [open, setOpen] = useState<Open>(null);
  const [tab, setTab] = useDetailTab(
    TABS,
    "overview",
    `/model-providers/${encodeURIComponent(provider.uid)}`,
  );

  const listed = endpoint.data?.models.length ?? 0;
  const offered = provider.models.length || listed;
  const count =
    endpoint.data && listed > 0 ? `${offered} / ${listed}` : offered ? `${offered}` : "";
  const rejectedStatus = status === "keyRejected" ? authStatusOf(endpoint.data?.message) : null;

  /** Test: ask the endpoint again and say what it answered. */
  const test = async () => {
    const r = await endpoint.refetch();
    const verdict = probeStatus({ data: r.data, error: r.error, pending: false });
    if (verdict === "reachable") {
      toast.success(t("providers.test.listed", { count: r.data?.models.length ?? 0 }));
    } else if (verdict === "keyRejected") {
      toast.error(
        t("providers.test.rejected", {
          status: authStatusOf(r.data?.message) ?? t("providers.test.noStatus"),
        }),
      );
    } else {
      toast.error(r.data?.message || t("providers.test.failed"));
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <ProviderDetailHeader
        provider={provider}
        status={status}
        onTest={() => void test()}
        onRefresh={() => void endpoint.refetch()}
        onEdit={() => setOpen("edit")}
        onDelete={() => setOpen("delete")}
      />
      {status === "keyRejected" ? (
        <KeyRejectedBanner
          status={rejectedStatus}
          use={use}
          onReplace={provider.secret_ref ? () => setOpen("replace") : undefined}
        />
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("providers.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="models">
            {t("providers.tabs.models")}
            {count ? <span className="text-2xs font-book text-text-subtle">{count}</span> : null}
          </TabsTrigger>
        </TabsList>
        <TabsContent value={tab} className="mt-5">
          {tab === "overview" ? (
            <ProviderOverview
              provider={provider}
              use={use}
              status={status}
              rejectedStatus={rejectedStatus}
              listed={endpoint.data ? listed : null}
              onReplaceKey={() => setOpen("replace")}
              onChooseModels={() => setTab("models")}
            />
          ) : (
            <ProviderModelsTab
              provider={provider}
              use={use}
              endpoint={endpoint}
              engineModel={engineModel}
              transcribeModel={transcribeModel}
            />
          )}
        </TabsContent>
      </Tabs>

      <EditProviderDialog
        open={open === "edit"}
        provider={provider}
        use={use}
        onClose={() => setOpen(null)}
        onSaved={() => void endpoint.refetch()}
      />
      <ReplaceKeyDialog
        open={open === "replace"}
        provider={provider}
        use={use}
        onClose={() => setOpen(null)}
      />
      <DeleteProviderDialog
        open={open === "delete"}
        provider={provider}
        use={use}
        onClose={() => setOpen(null)}
      />
    </div>
  );
}
