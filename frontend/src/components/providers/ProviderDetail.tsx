// src/components/providers/ProviderDetail.tsx — the open provider: header, the key-rejected banner, then one column.
//
// No tabs (canvas 2.2): Used by, Endpoint and Models are three sections read top to bottom at
// `/model-providers/<uid>`; what is wrong shows inside the section that has it. The dialogs the header and the Endpoint open —
// Edit, Replace key, Delete — are owned here, once.
import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { useToast } from "@/components/ui/toast";
import type { Provider } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { authStatusOf, probeStatus, type ProbeStatus } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { DeleteProviderDialog } from "./DeleteProviderDialog";
import { EditProviderDialog } from "./EditProviderDialog";
import { ProviderDetailHeader } from "./ProviderDetailHeader";
import { ProviderEndpoint } from "./ProviderEndpoint";
import { ProviderModels } from "./ProviderModels";
import { ProviderUsedBy } from "./ProviderUsedBy";
import { ReplaceKeyDialog } from "./ReplaceKeyDialog";

interface Props {
  provider: Provider;
  use: ProviderUse;
  endpoint: UseQueryResult<EndpointModelsOut>;
  status: ProbeStatus;
  engineModel: string | null;
  transcribeModel: string | null;
  latencyMs: number | null;
  /** A model id to find in Models (from the Usage tab's link). */
  focusModel?: string | null;
}

type Open = "edit" | "replace" | "delete" | null;

export function ProviderDetail({
  provider,
  use,
  endpoint,
  status,
  engineModel,
  transcribeModel,
  latencyMs,
  focusModel,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [open, setOpen] = useState<Open>(null);
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
    <div className="flex flex-col gap-8">
      <ProviderDetailHeader
        provider={provider}
        status={status}
        latencyMs={latencyMs}
        onTest={() => void test()}
        onEdit={() => setOpen("edit")}
        onDelete={() => setOpen("delete")}
      />
      <div className="flex flex-col gap-8">
        <ProviderUsedBy use={use} />
        <ProviderEndpoint
          provider={provider}
          use={use}
          status={status}
          rejectedStatus={rejectedStatus}
          reason={
            endpoint.error ? translateApiError(t, endpoint.error) : (endpoint.data?.message ?? "")
          }
          onReplaceKey={() => setOpen("replace")}
        />
        <ProviderModels
          provider={provider}
          use={use}
          endpoint={endpoint}
          engineModel={engineModel}
          transcribeModel={transcribeModel}
          focusModel={focusModel}
        />
      </div>

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
