// src/pages/UsagePage.tsx — /usage: subscription quota as each agent reports it, and metered API-key usage over a range.
//
// Two sections that load and fail independently. The range, the Agent and
// Provider filters and the breakdown live in the URL (`?range=`,
// `?from=&to=`, `?by=`, `?agent=`, `?provider=`) so a refresh or Back keeps
// them. The header's Refresh re-reads everything and asks Codex's app-server
// for fresh quota; Claude Code's row re-reads its own. The ⋯ beside the
// filters exports the current range and filters as CSV.
import { useState } from "react";
import { RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { QuotaSection } from "@/components/usage/QuotaSection";
import { UsageSection } from "@/components/usage/UsageSection";
import { useAgents } from "@/lib/hooks/useAgents";
import { useProviders } from "@/lib/hooks/useProviders";
import { useRetentionPolicies } from "@/lib/hooks/useRetention";
import {
  useExportUsageCsv,
  useInvalidateUsage,
  useRefreshQuota,
  useUsageQuota,
  useUsageSummary,
} from "@/lib/hooks/useUsage";
import type { Provider } from "@/lib/api/providers";
import type { UsageQuery } from "@/lib/api/usage";
import { presetById, vendorOf } from "@/lib/providers/presets";
import { activeProviderFor } from "@/lib/providers/usedBy";
import { formatClock } from "@/lib/usage/format";
import { addDays, localDay, readUsageQuery, writeUsageQuery } from "@/lib/usage/range";

/** Per-request detail window when the retention policy has not loaded. */
const DEFAULT_DETAIL_DAYS = 30;
/** Daily totals are kept this long: nothing in it means nothing ever went through the proxy. */
const DAILY_TOTALS_DAYS = 365;

/** The vendor a provider reads as: its preset's brand, else its own name. */
function vendorLabel(p: Provider): string {
  const vendor = vendorOf(p.base_url ?? "");
  return vendor === "custom" ? p.title || p.name : presetById(vendor).label;
}

export function UsagePage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const query = readUsageQuery(params);
  const summary = useUsageSummary(query);
  const byDay = useUsageSummary({ ...query, group_by: "day" });
  // Who sent API-key requests in the range, whatever the filters: the quota
  // rows' "some requests via API key".
  const byAgent = useUsageSummary({
    range: query.range,
    from: query.from,
    to: query.to,
    group_by: "agent",
  });
  // Whether anything ever went through the proxy: the first-run state.
  const today = new Date();
  const ever = useUsageSummary({
    range: "custom",
    from: localDay(addDays(today, 1 - DAILY_TOTALS_DAYS)),
    to: localDay(today),
    group_by: "agent",
  });
  const quota = useUsageQuota();
  const providers = useProviders();
  const agents = useAgents();
  const refresh = useRefreshQuota();
  const invalidate = useInvalidateUsage();
  const exportCsv = useExportUsageCsv();
  const retention = useRetentionPolicies();
  const [triedAt, setTriedAt] = useState<Date | null>(null);

  const policy = retention.data?.policies.find((p) => p.table_name === "mcp_invocations");
  const detailDays = policy ? policy.retention_days : DEFAULT_DETAIL_DAYS;
  const setQuery = (next: UsageQuery) => setParams(writeUsageQuery(params, next));
  const askCodex = () => {
    setTriedAt(new Date());
    refresh.mutate();
  };
  const updatedAt = Math.max(summary.dataUpdatedAt, quota.dataUpdatedAt);
  const now = new Date();
  const reason = refresh.data && !refresh.data.refreshed ? refresh.data.reason : null;

  const proxied = (providers.data ?? []).filter((p) => !p.local_runtime);
  // An agent runs on an API-key provider when its record names one that is
  // enabled and reaches it — the rule the agent's Model tab uses.
  const apiKeyVendorFor = (agentType: string) => {
    const agent = (agents.data ?? []).find((a) => a.type === agentType);
    const active = agent ? activeProviderFor(agent, proxied) : null;
    return active ? vendorLabel(active) : null;
  };
  const subscriptionAgents = new Set(
    (quota.data?.agents ?? [])
      .filter((a) => a.plan && !apiKeyVendorFor(a.agent_type))
      .map((a) => a.agent_type),
  );
  const sentViaApiKey = new Set(
    (byAgent.data?.rows ?? [])
      .filter((r) => r.agent_type && r.totals.requests > 0)
      .map((r) => r.agent_type as string),
  );
  const viaApiKey = new Set([...subscriptionAgents].filter((a) => sentViaApiKey.has(a)));

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("usage.title")}
        actions={
          <div className="flex items-center gap-2.5">
            {updatedAt > 0 ? (
              <span className="text-xs text-text-muted">
                {t("usage.updated", { time: formatClock(new Date(updatedAt), i18n.language) })}
              </span>
            ) : null}
            <Button
              variant="outline"
              size="sm"
              disabled={refresh.isPending}
              onClick={() => {
                invalidate();
                askCodex();
              }}
            >
              <RotateCw aria-hidden />
              {t("usage.refresh")}
            </Button>
          </div>
        }
      />
      <QuotaSection
        data={quota.data}
        isLoading={quota.isLoading}
        isError={quota.isError}
        onRetryLoad={() => void quota.refetch()}
        refresh={{ reason, triedAt, pending: refresh.isPending, onRetry: askCodex }}
        reread={{ pending: quota.isFetching, onReread: () => void quota.refetch() }}
        now={now}
        apiKeyVendorFor={apiKeyVendorFor}
        viaApiKey={viaApiKey}
      />
      <UsageSection
        query={query}
        onQueryChange={setQuery}
        detailDays={detailDays}
        summary={summary}
        byDay={byDay}
        neverUsed={ever.data?.totals.requests === 0}
        agentTypes={(quota.data?.agents ?? []).map((a) => a.agent_type)}
        providers={proxied.map((p) => ({ uid: p.uid, label: p.title || p.name }))}
        subscriptionAgents={subscriptionAgents}
        onExport={() => exportCsv.mutate(query)}
        exporting={exportCsv.isPending}
      />
    </div>
  );
}
