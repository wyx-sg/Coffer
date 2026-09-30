// src/components/usage/QuotaCard.tsx — one agent's subscription quota row: who, which login, each window, and as of when.
//
// The row takes one of five shapes (canvas 6.4): the agent runs on an API-key
// provider, so it has no subscription quota and is metered below; the manual
// Codex read failed, said inline with a retry; the agent reported windows;
// or no reading has arrived yet. A subscription agent that also sent requests
// through an API-key provider in the range carries a "via API key" tag.
// Claude Code's quota arrives with its responses, so its row re-reads what
// Coffer last stored; Codex's is asked of its app-server by the header's
// Refresh. Claude Code's no-reading row names the opt-in statusline wrapper:
// Coffer never installs it, so the page only says how.
import { AlertCircle, RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentQuota } from "@/lib/api/usage";
import { formatClock, formatMoment } from "@/lib/usage/format";
import { QuotaMeter } from "./QuotaMeter";
import { ViaApiKeyTag } from "./ViaApiKeyTag";

const STATUSLINE_COMMAND = "coffer usage statusline -- <your statusLine command>";

/** Why a manual Codex read did not happen, when it was tried, and how to try again. */
export interface RefreshState {
  reason: string | null;
  triedAt: Date | null;
  pending: boolean;
  onRetry: () => void;
}

/** Re-read the quota Coffer last stored (Claude Code's row). */
export interface RereadState {
  pending: boolean;
  onReread: () => void;
}

interface Props {
  quota: AgentQuota;
  now: Date;
  /** The vendor of the API-key provider the agent runs on; null on its own login. */
  apiKeyVendor?: string | null;
  /** The agent also sent requests through an API-key provider in the range. */
  viaApiKey?: boolean;
  /** Only Codex's row carries the manual app-server read. */
  refresh?: RefreshState;
  /** Only Claude Code's row re-reads on its own. */
  reread?: RereadState;
}

const KNOWN_REASONS = ["read_failed", "codex_unavailable", "no_subscription", "no_windows"];

const MIDDLE = "flex min-w-0 flex-col gap-0.5 md:col-span-2";
const RIGHT = "flex flex-col items-start gap-0.5 md:items-end md:text-right";

export function QuotaCard({ quota, now, apiKeyVendor, viaApiKey, refresh, reread }: Props) {
  const { t, i18n } = useTranslation();
  const name = agentTypeLabel(quota.agent_type);
  const planKey = ["claude_code", "codex"].includes(quota.agent_type) ? quota.agent_type : "other";
  const plan = apiKeyVendor
    ? t("usage.quota.plan.apiKey", { vendor: apiKeyVendor })
    : quota.plan
      ? t(`usage.quota.plan.${planKey}`, {
          plan: quota.plan[0].toUpperCase() + quota.plan.slice(1),
        })
      : t("usage.quota.plan.none");
  const newest = quota.windows.reduce<string | null>(
    (acc, w) => (acc === null || w.as_of > acc ? w.as_of : acc),
    null,
  );
  const source = quota.windows.find((w) => w.as_of === newest)?.source;
  const reason =
    !apiKeyVendor && refresh?.reason && refresh.reason !== "too_soon" ? refresh.reason : null;
  const muted = (text: string) => (
    <span className="whitespace-nowrap text-xs text-text-muted">{text}</span>
  );

  const middle = (() => {
    if (apiKeyVendor) {
      return (
        <div className={MIDDLE}>
          <span className="text-sm font-label text-text">{t("usage.quota.apiKey.title")}</span>
          <span className="text-xs leading-normal text-text-muted">
            {t("usage.quota.apiKey.body", { agent: name, vendor: apiKeyVendor })}
          </span>
        </div>
      );
    }
    if (reason) {
      return (
        <div className="flex min-w-0 items-center gap-2.5 md:col-span-2">
          <AlertCircle className="size-4 shrink-0 text-danger" aria-hidden />
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-sm text-text">{t("usage.quota.refreshFailed.title")}</span>
            <span className="text-xs text-text-muted">
              {t(`usage.quota.refreshFailed.${KNOWN_REASONS.includes(reason) ? reason : "other"}`)}
              {refresh?.triedAt
                ? ` ${t("usage.quota.lastTried", { time: formatClock(refresh.triedAt, i18n.language) })}`
                : null}
            </span>
          </span>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={refresh?.onRetry}
            disabled={refresh?.pending}
          >
            <RotateCw aria-hidden />
            {t("usage.quota.tryAgain")}
          </Button>
        </div>
      );
    }
    if (quota.has_value) {
      return (
        <div className="grid min-w-0 gap-x-7 gap-y-3 sm:grid-cols-2 md:col-span-2">
          {quota.windows.map((w) => (
            <QuotaMeter key={w.key} window={w} now={now} />
          ))}
        </div>
      );
    }
    return (
      <div className={MIDDLE}>
        <span className="text-sm text-text">{t("usage.quota.empty.title")}</span>
        <span className="text-xs text-text-muted">
          {t("usage.quota.empty.body", { agent: name })}
        </span>
        {quota.agent_type === "claude_code" ? (
          <span className="mt-1 flex flex-wrap items-center gap-1 text-xs text-text-muted">
            {t("usage.quota.statusline.lead")}
            <code className="rounded-sm bg-code px-1 font-mono text-2xs text-text">
              {STATUSLINE_COMMAND}
            </code>
            <HelpTip label={t("usage.quota.statusline.helpLabel")}>
              <p className="text-xs">{t("usage.quota.statusline.help")}</p>
            </HelpTip>
          </span>
        ) : null}
      </div>
    );
  })();

  const right = (() => {
    if (apiKeyVendor) return muted(t("usage.quota.metered"));
    if (reason) return muted(t("usage.quota.noReadingShort"));
    if (!quota.has_value || !newest) return muted(t("usage.quota.waiting"));
    return (
      <>
        <span className="flex items-center gap-1.5">
          {muted(t("usage.quota.asOf", { time: formatMoment(newest, now, i18n.language) }))}
          {reread ? (
            <Button
              variant="outline"
              size="sm"
              aria-label={t("usage.quota.rereadLabel", { agent: name })}
              disabled={reread.pending}
              onClick={reread.onReread}
            >
              <RotateCw aria-hidden />
              {t("usage.refresh")}
            </Button>
          ) : null}
        </span>
        {source ? (
          <span className="whitespace-nowrap text-2xs text-text-muted">
            {t(`usage.quota.source.${source}`, { defaultValue: source })}
          </span>
        ) : null}
      </>
    );
  })();

  return (
    <li className="grid grid-cols-1 items-center gap-x-7 gap-y-3 px-4 py-3 md:min-h-[76px] md:grid-cols-[208px_minmax(0,1fr)_minmax(0,1fr)_104px]">
      <div className="flex min-w-0 items-center gap-2.5">
        <AgentBadge type={quota.agent_type} tooltip={false} />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="text-sm font-label text-text">{name}</span>
          <span className="flex min-w-0 flex-wrap items-center gap-1 text-xs text-text-muted">
            <span className="truncate">
              {viaApiKey && !apiKeyVendor ? `${plan} · ${t("usage.quota.someRequests")}` : plan}
            </span>
            {viaApiKey && !apiKeyVendor ? <ViaApiKeyTag /> : null}
          </span>
        </span>
      </div>
      {middle}
      <div className={RIGHT}>{right}</div>
    </li>
  );
}
