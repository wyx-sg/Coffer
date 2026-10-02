// src/components/providers/ProviderDetail.tsx — the open provider: header, the key-rejected banner, then one column.
//
// No tabs (canvas 2.2): Used by, Endpoint and Models are three SettingsSection cards read top to bottom at
// `/model-providers/<uid>`. The dialogs the header and the Endpoint open —
// Edit, Replace key, Delete — are owned here, once.
import { useState } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { SETTINGS_STACK } from "@/components/settings/SettingsLayout";
import { useToast } from "@/components/ui/toast";
import type { Provider } from "@/lib/api/providers";
import type { EndpointModelsOut } from "@/lib/hooks/useModelIntrospection";
import { authStatusOf, probeStatus, type ProbeStatus } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { DeleteProviderDialog } from "./DeleteProviderDialog";
import { EditProviderDialog } from "./EditProviderDialog";
import { KeyRejectedBanner } from "./KeyRejectedBanner";
import { ProviderDetailHeader } from "./ProviderDetailHeader";
import { SectionStack } from "@/components/Section";
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
    <div className={SETTINGS_STACK}>
      <ProviderDetailHeader
        provider={provider}
        status={status}
        onTest={() => void test()}
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

      <SectionStack>
        <ProviderUsedBy use={use} failing={status === "keyRejected"} />
        <ProviderEndpoint
          provider={provider}
          use={use}
          rejectedStatus={rejectedStatus}
          onReplaceKey={() => setOpen("replace")}
        />
        <ProviderModels
          provider={provider}
          use={use}
          endpoint={endpoint}
          engineModel={engineModel}
          transcribeModel={transcribeModel}
        />
      </SectionStack>

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
