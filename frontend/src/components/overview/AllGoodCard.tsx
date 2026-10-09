// src/components/overview/AllGoodCard.tsx — "Nothing needs you": the calm card, with a sentence on what is fine.
//
// The sentence is built from lists the Overview already reads (agents, MCP
// servers, sync status; lib/overview/allGood),
// so it can only say what those lists say; while one is still loading its
// clause is left out. On the right, when the attention list was last checked
// (Overview board 1.2.03).
import { Check } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useAgents } from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { allGoodSummary } from "@/lib/overview/allGood";
import { formatClock } from "@/lib/overview/time";

export function AllGoodCard({ checkedAt }: { checkedAt: number }) {
  const { t } = useTranslation();
  const iso = checkedAt > 0 ? new Date(checkedAt).toISOString() : null;
  const agents = useAgents();
  const servers = useResources("mcp_server");
  const sync = useSyncStatus();
  const summary = allGoodSummary(t, {
    agents: agents.data?.length,
    servers: servers.data?.filter((s) => s.enabled).length,
    vaultInSync:
      sync.data !== undefined &&
      sync.data.configured &&
      !sync.data.problem &&
      sync.data.held === 0 &&
      sync.data.conflicts === 0,
  });
  return (
    <div className="flex items-center gap-[14px] rounded-xl border border-border bg-surface-raised px-[18px] py-4">
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
        <Check className="size-4" strokeWidth={2} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-[14px] font-semibold text-text">{t("overview.needsYou.empty.title")}</p>
        <p className="text-xs text-text-muted">{summary}</p>
      </div>
      {iso ? (
        <p className="ml-auto whitespace-nowrap text-xs text-text-subtle">
          {t("overview.needsYou.empty.checked")} <time dateTime={iso}>{formatClock(iso)}</time>
        </p>
      ) : null}
    </div>
  );
}
