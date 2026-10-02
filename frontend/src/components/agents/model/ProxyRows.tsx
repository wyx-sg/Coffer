// src/components/agents/model/ProxyRows.tsx — Fallback and Proxy token on the Model tab (boards 2.1.16, 2.1.19).
//
// Read-only: while the agent runs on an API-key or local provider it reaches
// it through Coffer's proxy, which fails over before the first byte to the
// next provider in the Model providers list that offers the same model (spec
// provider-switching "Order providers, and fail over in that order"). The
// agent's own proxy token is shown by its last four characters, with Rotate.
// The built-in login bypasses the proxy, so neither row shows for it.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import {
  useProxyAddress,
  useProxyRoute,
  useProxyTokenHint,
  useRotateProxyToken,
} from "@/lib/hooks/useProviderFallback";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] items-baseline gap-3 text-sm">
      <span className="text-xs text-text-muted">{label}</span>
      <div className="min-w-0 break-words text-xs text-text">{children}</div>
    </div>
  );
}

interface Props {
  agent: AgentOut;
  /** The model the agent runs now (its applied binding). */
  model: string | null;
  /** The agent runs on a provider, not its built-in login. */
  onProvider: boolean;
}

export function ProxyRows({ agent, model, onProvider }: Props) {
  const { t } = useTranslation();
  const route = useProxyRoute(agent.uid, model, onProvider);
  const hint = useProxyTokenHint(agent.uid, onProvider);
  const rotate = useRotateProxyToken(agent.uid);
  const address = useProxyAddress();
  const primary = route.data?.primary;
  if (!onProvider || !primary) return null;
  const fallbacks = route.data?.fallbacks ?? [];

  const fallback = primary.local
    ? t("agents.modelTab.proxy.noFallbackLocal", { provider: primary.name })
    : fallbacks.length === 0
      ? t("agents.modelTab.proxy.noFallback", { provider: primary.name })
      : t("agents.modelTab.proxy.fallback", {
          provider: primary.name,
          fallbacks: fallbacks.map((f) => f.name).join(", "),
          model: model ?? "",
        });

  return (
    <div className="flex flex-col gap-2">
      <Row label={t("agents.modelTab.proxy.fallbackLabel")}>{fallback}</Row>
      <Row label={t("agents.modelTab.proxy.tokenLabel")}>
        <span className="flex flex-wrap items-center gap-2">
          <span>
            {t("agents.modelTab.proxy.token", {
              agent: agentTypeLabel(agent.type),
              address,
            })}
            {hint.data ? <span className="font-mono"> · ••••{hint.data.last4}</span> : null}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            disabled={rotate.isPending}
            onClick={() => rotate.mutate()}
          >
            <RotateCw aria-hidden /> {t("agents.modelTab.proxy.rotate")}
          </Button>
        </span>
      </Row>
    </div>
  );
}
