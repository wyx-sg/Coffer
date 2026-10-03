// src/components/secret/SecretsBanners.tsx — the two banners above the Secrets list: no value on this Mac, then changes waiting for approval.
//
// Danger first, warning second, 8 apart (layout principle 16). Each has one action — Add value(s)
// opens the add-values dialog, Review opens the global approvals dialog — and an × that is
// Ignore (principle 19): the same state as Ignore on Overview, kept by the daemon under the
// attention item's key. Both come back when the set changes (the key is a fingerprint of it),
// and while ignored the page header says so. The banner reads the list's own rows, so what it
// counts never lags the table beneath it.
import { CircleAlert, ShieldCheck, X, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Approval, SecretRef } from "@/lib/api/secret";
import { openApprovalsSheet } from "@/lib/hooks/useApprovals";
import { useAttention } from "@/lib/hooks/useAttention";
import { useIgnoreAttention } from "@/lib/hooks/useAttentionIgnore";
import { joinNames } from "@/lib/skills/names";
import { cn } from "@/lib/utils";
import { approvalSecretName, citersOf, isMissingHere } from "./secretRows";

/** The attention reasons these banners share with Overview. */
const MISSING_REASON = "secret_missing_here";
const PENDING_REASON = "secret_approvals_pending";

/** Secrets the approvals banner names before "and N more". */
const NAMES_SHOWN = 1;

interface BannerProps {
  tone: "danger" | "warning";
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
  /** Ignore it; absent while the daemon's attention list has no such item. */
  onIgnore?: () => void;
  testId: string;
}

function Banner({
  tone,
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  onIgnore,
  testId,
}: BannerProps) {
  const { t } = useTranslation();
  return (
    <div
      role="status"
      data-testid={testId}
      className={cn(
        "flex items-center gap-3 rounded-xl border px-3.5 py-2.5",
        tone === "danger" ? "border-danger/30 bg-danger-soft" : "border-warning/30 bg-warning-soft",
      )}
    >
      <Icon
        className={cn("size-[15px] shrink-0", tone === "danger" ? "text-danger" : "text-warning")}
        aria-hidden
      />
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-sm font-semibold text-text">{title}</p>
        <p className="text-xs text-text-muted">{description}</p>
      </div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <Button variant="outline" size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
        {onIgnore ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("secrets.banner.ignore")}
                onClick={onIgnore}
              >
                <X aria-hidden />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t("secrets.banner.ignore")}</TooltipContent>
          </Tooltip>
        ) : null}
      </div>
    </div>
  );
}

/** "9+" past nine: a banner's count is the number of things that need you. */
const shownCount = (n: number) => (n > 9 ? "9+" : String(n));

interface Props {
  rows: SecretRef[];
  approvals: Approval[];
  onAddValues: () => void;
}

export function SecretsBanners({ rows, approvals, onAddValues }: Props) {
  const { t, i18n } = useTranslation();
  const attention = useAttention();
  const ignore = useIgnoreAttention();

  const items = attention.data?.items ?? [];
  const ignored = attention.data?.ignored ?? [];
  const keyOf = (reason: string) =>
    items.find((i) => i.kind === "secret" && i.reason_code === reason)?.key;
  const isIgnored = (reason: string) =>
    ignored.some((i) => i.kind === "secret" && i.reason_code === reason);
  const ignorer = (reason: string) => {
    const key = keyOf(reason);
    return key ? () => ignore.mutate(key) : undefined;
  };

  const missing = rows.filter(isMissingHere);
  const users = [...new Set(missing.flatMap((r) => citersOf(r).map((c) => c.name)))];
  const missingBanner =
    missing.length > 0 && !isIgnored(MISSING_REASON) ? (
      <Banner
        key="missing"
        testId="secrets-missing-banner"
        tone="danger"
        icon={CircleAlert}
        title={t("secrets.banner.missing.title", {
          count: missing.length,
          n: shownCount(missing.length),
        })}
        description={
          users.length === 0
            ? t("secrets.banner.missing.noUsers")
            : t("secrets.banner.missing.body", {
                count: missing.length,
                names: joinNames(users, i18n.language),
              })
        }
        actionLabel={t("secrets.banner.missing.action", { count: missing.length })}
        onAction={onAddValues}
        onIgnore={ignorer(MISSING_REASON)}
      />
    ) : null;

  const names = [...new Set(approvals.map((a) => approvalSecretName(a, rows)))];
  const listed = names.slice(0, NAMES_SHOWN).join(", ");
  const more = names.length - NAMES_SHOWN;
  const named = more > 0 ? t("secrets.banner.waiting.andMore", { names: listed, n: more }) : listed;
  const op = approvals.every((a) => a.op === approvals[0]?.op) ? approvals[0]?.op : "mixed";
  const waitingBanner =
    approvals.length > 0 && !isIgnored(PENDING_REASON) ? (
      <Banner
        key="waiting"
        testId="pending-approvals-entry"
        tone="warning"
        icon={ShieldCheck}
        title={t("secrets.banner.waiting.title", {
          count: approvals.length,
          n: shownCount(approvals.length),
        })}
        description={`${t(`secrets.banner.waiting.what.${op}`, {
          count: approvals.length,
          names: named,
        })} ${t("secrets.approvals.hintShell")}`}
        actionLabel={t("secrets.approvals.review")}
        onAction={openApprovalsSheet}
        onIgnore={ignorer(PENDING_REASON)}
      />
    ) : null;

  if (!missingBanner && !waitingBanner) return null;
  return (
    <div className="flex flex-col gap-2">
      {missingBanner}
      {waitingBanner}
    </div>
  );
}
