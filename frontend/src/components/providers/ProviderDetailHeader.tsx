// src/components/providers/ProviderDetailHeader.tsx — the open provider's header: mark, name, health, wire · URL, actions.
//
// The health pill is read from the endpoint probe that runs when the provider
// opens: Reachable, Key rejected or Unreachable. The actions keep the detail
// page's fixed order — reach (the shared ScopeControl, the one place the
// provider's reach and enabled state are shown and changed), Test, Edit — and
// the "⋯" menu: Delete provider (Refresh models is the Models section's button).
import { useTranslation } from "react-i18next";
import { Pencil, Plug } from "lucide-react";

import { ScopeControl } from "@/components/ScopeControl";
import { StatusPill } from "@/components/status/StatusPill";
import type { StatusTone } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { TruncatedText } from "@/components/ui/truncated-text";
import { ActionMenu } from "@/components/ui/menu";
import type { Provider } from "@/lib/api/providers";
import { PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProbeStatus } from "@/lib/providers/probeStatus";
import { displayName } from "@/lib/resourceTitle";
import { ProviderMark } from "./ProviderMark";

const TONE: Record<ProbeStatus, StatusTone> = {
  checking: "off",
  reachable: "ok",
  keyRejected: "err",
  unreachable: "err",
};

interface Props {
  provider: Provider;
  status: ProbeStatus;
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function ProviderDetailHeader({ provider, status, onTest, onEdit, onDelete }: Props) {
  const { t } = useTranslation();
  const name = displayName(provider);
  return (
    <header className="flex min-w-0 items-center gap-3" data-testid="provider-header">
      <ProviderMark provider={provider} size="lg" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="min-w-0 truncate text-lg font-bold text-text">{name}</h2>
          <StatusPill tone={TONE[status]}>{t(`providers.status.${status}`)}</StatusPill>
        </div>
        <TruncatedText
          text={`${t(PROTOCOL_LABEL_KEY[provider.protocol])} · ${provider.base_url}`}
          className="text-xs text-text-muted"
        />
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        <ScopeControl kind="provider" uid={provider.uid} enabled={provider.enabled} />
        <Button size="sm" variant="outline" onClick={onTest} disabled={status === "checking"}>
          <Plug aria-hidden /> {t("providers.actions.test")}
        </Button>
        <Button size="sm" variant="outline" onClick={onEdit}>
          <Pencil aria-hidden /> {t("common.edit")}
        </Button>
        <ActionMenu
          label={t("providers.actions.more", { name })}
          actions={[
            {
              key: "delete",
              label: t("providers.actions.delete"),
              onSelect: onDelete,
              destructive: true,
              separated: true,
            },
          ]}
        />
      </span>
    </header>
  );
}
