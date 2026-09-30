// src/components/providers/ProviderListRow.tsx — one provider in the list pane: mark, name, what it offers, who runs on it.
//
// The sub-line is the protocol and the model offer — "N models" when the
// provider curates, "All models" when it does not, and "Coffer's engine only"
// for an Ollama-protocol provider, which reaches no agent. The marks at the
// end are the agents running on it (the Used-by rule) and the Coffer badges.
// The row links to the provider by uid; the open one is highlighted.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import type { Provider } from "@/lib/api/providers";
import { PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { displayName } from "@/lib/resourceTitle";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { CofferUseBadge } from "./CofferUseBadge";
import { ProviderMark } from "./ProviderMark";

interface Props {
  provider: Provider;
  use: ProviderUse;
  selected: boolean;
  /** Set on the open row when its probe found the key rejected ("401"/"403", or ""). */
  rejected?: string | null;
  /** The drag handle, before the link (list order is fallback priority). */
  handle?: ReactNode;
}

function useOfferLabel(provider: Provider): string {
  const { t } = useTranslation();
  if (provider.protocol === "ollama") return t("providers.list.engineOnly");
  const n = provider.models.length;
  return n === 0 ? t("providers.list.allModels") : t("providers.list.models", { count: n });
}

export function ProviderListRow({ provider, use, selected, rejected, handle }: Props) {
  const { t } = useTranslation();
  const offer = useOfferLabel(provider);
  const sub =
    rejected != null
      ? [t("providers.status.keyRejected"), rejected].filter(Boolean).join(" · ")
      : `${t(PROTOCOL_LABEL_KEY[provider.protocol])} · ${offer}`;
  const link = (
    <Link
      to={`/model-providers/${encodeURIComponent(provider.uid)}`}
      aria-current={selected ? "page" : undefined}
      data-testid="provider-row"
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-text no-underline outline-none",
        "hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring",
        selected && "bg-surface-selected hover:bg-surface-selected",
      )}
    >
      <ProviderMark provider={provider} size="md" withWord={false} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-sm font-label">{displayName(provider)}</span>
        <span
          className={cn(
            "truncate text-xs",
            rejected != null ? toneTextClass("error") : "text-text-muted",
          )}
        >
          {sub}
        </span>
      </span>
      <span className="inline-flex shrink-0 items-center gap-1">
        {use.agents.map(({ agent }) => (
          <AgentBadge key={agent.uid} type={agent.type} size="sm" />
        ))}
        {use.engine ? <CofferUseBadge use="engine" /> : null}
        {use.transcribe ? <CofferUseBadge use="transcribe" /> : null}
      </span>
    </Link>
  );
  if (!handle) return link;
  return (
    <div className="flex items-center gap-0.5">
      {handle}
      <div className="min-w-0 flex-1">{link}</div>
    </div>
  );
}
