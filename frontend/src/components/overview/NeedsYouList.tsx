// src/components/overview/NeedsYouList.tsx — "Needs you": one row per problem across every area, most urgent first.
//
// Each row is a dot, the item's name (a link to its page) over its kind, the
// daemon's reason as-is, when it started, and one action that opens the page
// where the person can act. Rows clear themselves: an attention change on the
// event stream refetches the list (useDaemonEvents). A source that could not
// be checked says so above the rows, so a short list is never mistaken for a
// complete one.
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAttention, type AttentionItem } from "@/lib/hooks/useAttention";
import {
  actionLabelKey,
  actionPage,
  itemPage,
  severityTone,
  sortAttention,
} from "@/lib/overview/attention";
import { kindMeta } from "@/lib/overview/kinds";
import { describeSince, formatClock } from "@/lib/overview/time";
import { cn } from "@/lib/utils";

const ROW_GRID =
  "grid grid-cols-[8px_minmax(0,1fr)] items-center gap-x-3 gap-y-1 px-4 py-3 md:grid-cols-[8px_196px_minmax(0,1fr)_104px_176px]";
// On a phone everything after the dot stacks in the second column.
const CELL = "col-start-2 md:col-start-auto";

export function NeedsYouList() {
  const { t } = useTranslation();
  const attention = useAttention();
  const items = attention.data ? sortAttention(attention.data.items) : [];
  const errors = attention.data?.errors ?? [];

  return (
    <section aria-labelledby="overview-needs-you" className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 id="overview-needs-you" className="text-sm font-semibold">
          {t("overview.needsYou.title")}
        </h2>
        {attention.data && items.length > 0 ? (
          <span className="rounded-sm bg-chip px-1.5 text-2xs font-heavy text-text-muted">
            {items.length}
          </span>
        ) : null}
        <span className="ml-auto text-xs text-text-subtle">{t("overview.needsYou.order")}</span>
      </div>

      {attention.isPending ? (
        <ul
          aria-busy
          className="divide-y divide-border-subtle rounded-xl border border-border-subtle"
        >
          {[0, 1, 2].map((i) => (
            <li key={i} className={ROW_GRID}>
              <Skeleton className="size-2 rounded-full" />
              <Skeleton className={cn(CELL, "h-4 w-32")} />
              <Skeleton className={cn(CELL, "h-4 w-full")} />
            </li>
          ))}
        </ul>
      ) : attention.isError ? (
        <div className="rounded-xl border border-border-subtle">
          <EmptyState
            tone="error"
            icon={AlertTriangle}
            title={t("overview.needsYou.error")}
            description={translateApiError(t, attention.error)}
            action={
              <Button variant="outline" size="sm" onClick={() => void attention.refetch()}>
                {t("overview.retry")}
              </Button>
            }
          />
        </div>
      ) : (
        <>
          {errors.map((e) => (
            <p key={e.source} className="flex items-start gap-2 text-xs text-warning">
              <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
              {t("overview.needsYou.sourceFailed", {
                area: t(`overview.sources.${e.source}`, { defaultValue: e.source }),
              })}
            </p>
          ))}
          {items.length > 0 ? (
            <ul className="divide-y divide-border-subtle rounded-xl border border-border-subtle bg-surface-raised">
              {items.map((item, i) => (
                <NeedsYouRow
                  key={`${item.kind}:${item.uid ?? ""}:${item.reason_code}:${i}`}
                  item={item}
                />
              ))}
            </ul>
          ) : errors.length === 0 ? (
            <AllGood checkedAt={attention.dataUpdatedAt} />
          ) : null}
        </>
      )}
    </section>
  );
}

function NeedsYouRow({ item }: { item: AttentionItem }) {
  const { t } = useTranslation();
  const meta = kindMeta(item.kind);
  const KindIcon = meta.icon;
  const since = describeSince(item.since);
  const action = t(actionLabelKey(item.action.verb));
  return (
    <li className={ROW_GRID}>
      <span
        role="img"
        aria-label={t(
          item.severity === "error" ? "overview.needsYou.failing" : "overview.needsYou.attention",
        )}
        className="inline-flex"
      >
        <StatusDot tone={severityTone(item.severity)} className="size-2" />
      </span>
      <Link to={itemPage(item)} className={cn(CELL, "group min-w-0")}>
        <span
          className={cn(
            "block truncate text-text group-hover:underline",
            meta.identifier ? "font-mono text-xs font-medium" : "text-sm font-label",
          )}
        >
          {item.title}
        </span>
        <span className="flex items-center gap-1 text-2xs text-text-muted">
          <KindIcon className="size-3" aria-hidden />
          {t(meta.labelKey)}
        </span>
      </Link>
      <p className={cn(CELL, "text-sm text-text-muted")}>{item.reason}</p>
      <p className={cn(CELL, "text-xs text-text-subtle")}>
        {since ? <SinceText since={since} iso={item.since ?? ""} /> : null}
      </p>
      <div className={cn(CELL, "md:justify-self-end")}>
        <Button asChild variant="outline" size="sm">
          <Link
            to={actionPage(item)}
            aria-label={t("overview.needsYou.actionFor", { action, name: item.title })}
          >
            {action}
          </Link>
        </Button>
      </div>
    </li>
  );
}

function SinceText({
  since,
  iso,
}: {
  since: NonNullable<ReturnType<typeof describeSince>>;
  iso: string;
}) {
  const { t } = useTranslation();
  if (since.kind === "yesterday") return <>{t("overview.needsYou.sinceYesterday")}</>;
  return (
    <>
      {t("overview.needsYou.since")}{" "}
      <time dateTime={iso}>{since.kind === "today" ? since.time : since.date}</time>
    </>
  );
}

function AllGood({ checkedAt }: { checkedAt: number }) {
  const { t } = useTranslation();
  const iso = checkedAt > 0 ? new Date(checkedAt).toISOString() : null;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border-subtle bg-surface-raised px-4 py-4">
      <CheckCircle2 className="mt-px size-4 shrink-0 text-text-subtle" aria-hidden />
      <div className="space-y-0.5">
        <p className="text-sm font-semibold">{t("overview.needsYou.empty.title")}</p>
        <p className="text-sm text-text-muted">{t("overview.needsYou.empty.body")}</p>
        {iso ? (
          <p className="text-xs text-text-subtle">
            {t("overview.needsYou.empty.checked")} <time dateTime={iso}>{formatClock(iso)}</time>
          </p>
        ) : null}
      </div>
    </div>
  );
}
