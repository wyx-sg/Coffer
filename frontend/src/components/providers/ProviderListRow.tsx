// src/components/providers/ProviderListRow.tsx — one provider in the list pane: mark, name, what it offers, who runs on it.
//
// The sub-line is the protocol and the model offer — "N models" when the
// provider curates, "All models" when it does not. The marks at the
// end are the agents running on it (the Used-by rule) and the Coffer badges.
// The row links to the provider by uid; the open one is highlighted.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import type { Provider } from "@/lib/api/providers";
import { PROTOCOL_LABEL_KEY } from "@/lib/providers/presets";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { TruncatedText } from "@/components/ui/truncated-text";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";
import { CofferUseBadge } from "./CofferUseBadge";
import { ProviderMark } from "./ProviderMark";

interface Props {
  provider: Provider;
  use: ProviderUse;
  selected: boolean;
  /** What is wrong with the connection, when something is: the sub-line says so, in red. */
  problem?: "keyRejected" | "unreachable" | null;
}

function useOfferLabel(provider: Provider): string {
  const { t } = useTranslation();
  const n = provider.models.length;
  return n === 0 ? t("providers.list.allModels") : t("providers.list.models", { count: n });
}

/** "Anthropic", "OpenAI-compatible" or "Local runtime": what the sub-line leads with. */
function useKindLabel(provider: Provider): string {
  const { t } = useTranslation();
  return provider.local_runtime
    ? t("providers.list.localRuntime")
    : t(PROTOCOL_LABEL_KEY[provider.protocol]);
}

export function ProviderListRow({ provider, use, selected, problem }: Props) {
  const { t } = useTranslation();
  const offer = useOfferLabel(provider);
  const kind = useKindLabel(provider);
  const sub = problem ? t(`providers.status.${problem}`) : `${kind} · ${offer}`;
  return (
    <Link
      to={`/model-providers/${encodeURIComponent(provider.uid)}`}
      aria-current={selected ? "page" : undefined}
      data-testid="provider-row"
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-text no-underline outline-none",
        "transition-colors duration-fast hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring",
        selected && "bg-surface-selected hover:bg-surface-selected",
      )}
    >
      <ProviderMark provider={provider} size="md" withWord={false} />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <TruncatedText text={provider.name} className="text-sm font-label" />
        <TruncatedText
          text={sub}
          className={cn("text-xs", problem ? toneTextClass("error") : "text-text-muted")}
        />
      </span>
      <span className="inline-flex shrink-0 items-center gap-1">
        {use.agents.map(({ agent }) => (
          <AgentBadge key={agent.uid} type={agent.type} size="sm" />
        ))}
        {use.transcribe ? <CofferUseBadge use="transcribe" /> : null}
      </span>
    </Link>
  );
}
