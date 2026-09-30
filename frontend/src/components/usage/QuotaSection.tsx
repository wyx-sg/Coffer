// src/components/usage/QuotaSection.tsx — "Subscription quota": one row per agent type the daemon reports quota for.
//
// Loads and fails on its own, so a quota error never blanks the API-key
// section below it (and vice versa).
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { QuotaList } from "@/lib/api/usage";
import { QuotaCard, type RefreshState } from "./QuotaCard";

interface Props {
  data: QuotaList | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetryLoad: () => void;
  refresh: RefreshState;
  now: Date;
}

export function QuotaSection({ data, isLoading, isError, onRetryLoad, refresh, now }: Props) {
  const { t } = useTranslation();
  return (
    <section aria-label={t("usage.quota.title")} className="flex flex-col gap-2">
      <div className="flex min-h-7 flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-text">{t("usage.quota.title")}</h2>
        <HelpTip label={t("usage.quota.helpLabel")}>
          <p className="text-xs">{t("usage.quota.help1")}</p>
          <p className="text-xs">{t("usage.quota.help2")}</p>
        </HelpTip>
        <span className="text-xs text-text-muted">{t("usage.quota.subtitle")}</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        {isLoading ? (
          <div className="flex flex-col gap-3 p-4" data-testid="quota-loading">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : isError || !data ? (
          <EmptyState
            tone="error"
            title={t("usage.quota.error")}
            className="min-h-0 py-6"
            action={
              <Button variant="outline" size="sm" onClick={onRetryLoad}>
                {t("common.retry")}
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-border-subtle">
            {data.agents.map((q) => (
              <QuotaCard
                key={q.agent_type}
                quota={q}
                now={now}
                refresh={q.agent_type === "codex" ? refresh : undefined}
              />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
