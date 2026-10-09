// src/components/providers/ProviderDetailHeader.tsx — the open provider's header: mark, name, health, agents · host · latency, actions.
//
// The health pill is read from the endpoint probe that runs when the provider
// opens: Reachable, Key rejected or Unreachable. The meta line is the agents
// its addresses serve, the host and — when the endpoint answered — how long it
// took; an endpoint that does not answer has no latency to show. The actions
// keep the detail page's fixed order — Test, Edit — and the "⋯" menu: Delete
// provider (Refresh models is the Models section's button).
import { useTranslation } from "react-i18next";
import { Pencil, Zap } from "lucide-react";

import { StatusPill } from "@/components/status/StatusPill";
import type { StatusTone } from "@/lib/statusTone";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import type { Provider } from "@/lib/api/providers";
import { agentTypeLabel } from "@/lib/agents/display";
import type { ProbeStatus } from "@/lib/providers/probeStatus";
import { displayName } from "@/lib/resourceTitle";
import { ProviderMark } from "./ProviderMark";

const TONE: Record<ProbeStatus, StatusTone> = {
  checking: "off",
  reachable: "ok",
  keyRejected: "err",
  unreachable: "err",
};

/** `host[:port]` of a base URL, or the URL itself when it does not parse. */
function hostOf(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

interface Props {
  provider: Provider;
  status: ProbeStatus;
  /** How long the last probe took; shown only while the endpoint answers. */
  latencyMs: number | null;
  onTest: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

export function ProviderDetailHeader({
  provider,
  status,
  latencyMs,
  onTest,
  onEdit,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const name = displayName(provider);
  const answered = status === "reachable" || status === "keyRejected";
  // Which agents can use it follows from its addresses; there is no switch or
  // scope to set (ADR provider-reach-is-what-its-addresses-serve).
  const served = (provider.served_agents ?? []).map(agentTypeLabel);
  return (
    <header className="flex min-w-0 items-center gap-3" data-testid="provider-header">
      <ProviderMark provider={provider} size="lg" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <h2 className="min-w-0 truncate text-lg font-bold text-text">{name}</h2>
          <StatusPill tone={TONE[status]}>{t(`providers.status.${status}`)}</StatusPill>
        </div>
        <p className="min-w-0 truncate text-sm text-text-subtle">
          {served.length > 0
            ? t("providers.served", { agents: served.join(", ") })
            : t("providers.servedNone")}{" "}
          · <span className="font-mono">{hostOf(provider.base_url)}</span>
          {answered && latencyMs !== null ? ` · ${t("providers.latency", { ms: latencyMs })}` : ""}
        </p>
      </div>
      <span className="inline-flex shrink-0 items-center gap-2">
        <Button size="sm" variant="outline" onClick={onTest} disabled={status === "checking"}>
          <Zap aria-hidden /> {t("providers.actions.test")}
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
            },
          ]}
        />
      </span>
    </header>
  );
}
