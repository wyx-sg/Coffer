// src/components/usage/QuotaCard.tsx — one agent's subscription quota row: who, which plan, each window, and as of when.
//
// With no reading yet the row says when one will appear. Codex's row also
// carries why the last manual read did not happen (app-server unreachable,
// asked too soon), with a retry. Claude Code's no-reading row offers the
// opt-in statusline wrapper as a hand-off (the row's `handoff` prompt): Coffer
// never installs it, so the person's agent edits Claude Code's settings.
import { RotateCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentQuota } from "@/lib/api/usage";
import { formatClock, formatMoment } from "@/lib/usage/format";
import { QuotaMeter } from "./QuotaMeter";

/** Why a manual Codex read did not happen, when it was tried, and how to try again. */
export interface RefreshState {
  reason: string | null;
  triedAt: Date | null;
  pending: boolean;
  onRetry: () => void;
}

interface Props {
  quota: AgentQuota;
  now: Date;
  /** Only Codex's row is refreshable. */
  refresh?: RefreshState;
}

const KNOWN_REASONS = ["read_failed", "codex_unavailable", "no_subscription", "no_windows"];

export function QuotaCard({ quota, now, refresh }: Props) {
  const { t, i18n } = useTranslation();
  const name = agentTypeLabel(quota.agent_type);
  const planKey = ["claude_code", "codex"].includes(quota.agent_type) ? quota.agent_type : "other";
  const plan = quota.plan
    ? t(`usage.quota.plan.${planKey}`, { plan: quota.plan[0].toUpperCase() + quota.plan.slice(1) })
    : t("usage.quota.plan.none");
  const newest = quota.windows.reduce<string | null>(
    (acc, w) => (acc === null || w.as_of > acc ? w.as_of : acc),
    null,
  );
  const source = quota.windows.find((w) => w.as_of === newest)?.source;
  const reason = refresh?.reason && refresh.reason !== "too_soon" ? refresh.reason : null;

  return (
    <li className="grid grid-cols-1 items-center gap-x-7 gap-y-3 px-4 py-3 md:grid-cols-[208px_minmax(0,1fr)_minmax(0,1fr)_104px]">
      <div className="flex min-w-0 items-center gap-2.5">
        <AgentBadge type={quota.agent_type} tooltip={false} />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="text-sm font-label text-text">{name}</span>
          <span className="truncate text-xs text-text-muted">{plan}</span>
        </span>
      </div>

      {reason ? (
        <div className="flex min-w-0 flex-col gap-1 md:col-span-2">
          <span className="text-sm font-label text-danger">
            {t("usage.quota.refreshFailed.title")}
          </span>
          <span className="text-xs text-text-muted">
            {t(`usage.quota.refreshFailed.${KNOWN_REASONS.includes(reason) ? reason : "other"}`)}
            {refresh?.triedAt
              ? ` ${t("usage.quota.lastTried", { time: formatClock(refresh.triedAt, i18n.language) })}`
              : null}
          </span>
        </div>
      ) : quota.has_value ? (
        <div className="grid min-w-0 gap-x-7 gap-y-3 sm:grid-cols-2 md:col-span-2">
          {quota.windows.map((w) => (
            <QuotaMeter key={w.key} window={w} now={now} />
          ))}
        </div>
      ) : (
        <div className="flex min-w-0 flex-col gap-1 md:col-span-2">
          <span className="text-sm font-label text-text">{t("usage.quota.empty.title")}</span>
          <span className="text-xs text-text-muted">
            {t("usage.quota.empty.body", { agent: name })}
          </span>
          {quota.handoff ? (
            <div className="flex flex-col items-start gap-1.5">
              <span className="flex flex-wrap items-center gap-1 text-xs text-text-muted">
                {t("usage.quota.statusline.lead")}
                <HelpTip label={t("usage.quota.statusline.helpLabel")}>
                  <p className="text-xs">{t("usage.quota.statusline.help")}</p>
                </HelpTip>
              </span>
              <AgentHandoff prompt={quota.handoff.prompt} size="sm" />
            </div>
          ) : null}
        </div>
      )}

      <div className="flex flex-col items-start gap-0.5 md:items-end md:text-right">
        {refresh && (reason || !quota.has_value) ? (
          <Button variant="outline" size="sm" onClick={refresh.onRetry} disabled={refresh.pending}>
            <RotateCw aria-hidden />
            {t("usage.quota.tryAgain")}
          </Button>
        ) : newest ? (
          <>
            <span className="whitespace-nowrap text-xs text-text-muted">
              {t("usage.quota.asOf", { time: formatMoment(newest, now, i18n.language) })}
            </span>
            {source ? (
              <span className="whitespace-nowrap text-2xs text-text-muted">
                {t(`usage.quota.source.${source}`, { defaultValue: source })}
              </span>
            ) : null}
          </>
        ) : null}
      </div>
    </li>
  );
}
