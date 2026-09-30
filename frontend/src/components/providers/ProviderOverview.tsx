// src/components/providers/ProviderOverview.tsx — a provider's Overview: Used by, Endpoint, and the models it offers.
import { useTranslation } from "react-i18next";
import { ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Provider } from "@/lib/api/providers";
import type { ProbeStatus } from "@/lib/providers/probeStatus";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { ProviderEndpoint } from "./ProviderEndpoint";
import { ProviderUsedBy } from "./ProviderUsedBy";
import { Section } from "./Section";

const CHIPS = 7;

interface Props {
  provider: Provider;
  use: ProviderUse;
  status: ProbeStatus;
  rejectedStatus: string | null;
  /** How many models the endpoint lists, once the probe has answered. */
  listed: number | null;
  onReplaceKey: () => void;
  onChooseModels: () => void;
}

export function ProviderOverview({
  provider,
  use,
  status,
  rejectedStatus,
  listed,
  onReplaceKey,
  onChooseModels,
}: Props) {
  const { t } = useTranslation();
  const ids = provider.models.map((m) => m.id);
  const offered =
    ids.length === 0
      ? listed
        ? t("providers.overview.allOfListed", { count: listed })
        : t("providers.overview.all")
      : listed
        ? t("providers.overview.nOfListed", { n: ids.length, count: listed })
        : t("providers.overview.n", { count: ids.length });

  return (
    <div className="flex flex-col gap-5">
      <ProviderUsedBy use={use} failing={status === "keyRejected"} />
      <ProviderEndpoint
        provider={provider}
        use={use}
        rejectedStatus={rejectedStatus}
        onReplaceKey={onReplaceKey}
      />
      <Section
        title={t("providers.overview.models")}
        aside={
          <>
            <span className="text-xs text-text-muted">{offered}</span>
            <Button
              variant="link"
              size="sm"
              className="ml-auto h-auto px-0"
              onClick={onChooseModels}
            >
              <ListChecks aria-hidden /> {t("providers.overview.choose")}
            </Button>
          </>
        }
      >
        {ids.length === 0 ? (
          <p className="text-xs text-text-muted">{t("providers.overview.unrestricted")}</p>
        ) : (
          <div className="flex flex-wrap items-center gap-1.5">
            {ids.slice(0, CHIPS).map((id) => (
              <span
                key={id}
                className="inline-flex h-5 items-center whitespace-nowrap rounded-sm bg-chip px-[7px] font-mono text-2xs text-text-muted"
              >
                {id}
              </span>
            ))}
            {ids.length > CHIPS ? (
              <span className="text-xs text-text-muted">+{ids.length - CHIPS}</span>
            ) : null}
          </div>
        )}
      </Section>
    </div>
  );
}
