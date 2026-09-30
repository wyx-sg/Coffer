// frontend/src/components/memory/MemoryDeliveriesSection.tsx — "Delivered at session start · Last 7 days".
//
// One row per agent (web-ui "Show memory delivery on the Memory page"): how
// often memory reached it in the window, how many distinct memories its
// sessions read and when it was last delivered to. An agent with no delivery
// reads "Not delivered in the last 7 days" and nothing more — the delivery
// hook's state and Repair live only on the agent's own page. A read count the
// daemon cannot compute (it cannot read that agent's transcripts) reads as
// unavailable, never as zero.
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { sortAgents } from "@/components/agent/agentOrder";
import { formatRelativeTime } from "@/components/agents/list/relativeTime";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { translateApiError } from "@/lib/api/errors";
import type { AgentDeliveryStatsOut } from "@/lib/api/memoryTypes";
import { useMemoryDeliveries } from "@/lib/hooks/useMemory";
import { formatDateTime } from "@/lib/utils";
import { MemorySection } from "./MemorySection";

const DEFAULT_WINDOW_DAYS = 7;

export function MemoryDeliveriesSection() {
  const { t } = useTranslation();
  const { data, isPending, error } = useMemoryDeliveries();
  const days = data?.window_days ?? DEFAULT_WINDOW_DAYS;
  const agents = sortAgents(
    (data?.agents ?? []).map((a) => ({ ...a, type: a.agent_type, name: a.agent_name })),
  );

  return (
    <MemorySection
      title={t("memory.deliveries.title")}
      meta={t("memory.deliveries.window", { count: days })}
      testId="memory-deliveries"
    >
      <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised">
        {isPending ? (
          <div className="space-y-2 p-3.5">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-5 w-1/2" />
          </div>
        ) : error ? (
          <p className="px-3.5 py-3 text-sm text-danger">
            {t("memory.deliveries.loadFailed")} {translateApiError(t, error)}
          </p>
        ) : agents.length === 0 ? (
          <p className="px-3.5 py-3 text-sm text-text-muted">{t("memory.deliveries.none")}</p>
        ) : (
          <ul>
            {agents.map((a) => (
              <DeliveryRow key={a.agent_uid} stats={a} days={days} />
            ))}
          </ul>
        )}
      </div>
    </MemorySection>
  );
}

function DeliveryRow({ stats, days }: { stats: AgentDeliveryStatsOut; days: number }) {
  const { t, i18n } = useTranslation();
  const delivered = stats.deliveries > 0;
  return (
    <li
      data-testid={`memory-delivery-${stats.agent_type}`}
      className="flex min-h-11 flex-wrap items-center gap-x-2.5 gap-y-1 border-t border-border-subtle px-3.5 py-2 first:border-t-0"
    >
      <AgentBadge type={stats.agent_type} name={stats.agent_name} size="sm" tooltip={false} />
      <span className="w-28 shrink-0 text-sm font-label text-text">{stats.agent_name}</span>
      {delivered ? (
        <span className="text-xs text-text-muted">
          {t("memory.deliveries.delivered", { count: stats.deliveries, days })}
          {" · "}
          {stats.notes_read_status === "available" && stats.notes_read !== null ? (
            t("memory.deliveries.read", { count: stats.notes_read })
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span tabIndex={0} className="cursor-default underline decoration-dotted">
                  {t("memory.deliveries.readUnavailable")}
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                {t("memory.deliveries.readUnavailableHint")}
              </TooltipContent>
            </Tooltip>
          )}
          {stats.last_delivered_at ? (
            <>
              {" · "}
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0} className="cursor-default">
                    {t("memory.deliveries.last", {
                      when: formatRelativeTime(stats.last_delivered_at, i18n.language),
                    })}
                  </span>
                </TooltipTrigger>
                <TooltipContent>{formatDateTime(stats.last_delivered_at)}</TooltipContent>
              </Tooltip>
            </>
          ) : null}
        </span>
      ) : (
        <span className="text-xs text-text-muted">
          {t("memory.deliveries.notDelivered", { days })}
        </span>
      )}
    </li>
  );
}
