// src/components/overview/NeedsYouList.tsx — "Needs you": one row per problem across every area, most urgent first.
//
// Rows are NeedsYouRow. They clear themselves: an attention change on the
// event stream refetches the list (useDaemonEvents). A source that could not
// be checked says so above the rows, so a short list is never mistaken for a
// complete one. Items ignored on this machine (an agent left unconnected on
// purpose) are the daemon's `ignored` list, kept out of `items` and the
// counts the sidebar and the menu bar read; they are counted under the list —
// "1 ignored · Show" — and Show lists them again, muted, each with Stop
// ignoring. With nothing left, the list is the calm "Nothing needs you" card.
import { AlertTriangle, Check } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAgents } from "@/lib/hooks/useAgents";
import { useAttention, type AttentionItem } from "@/lib/hooks/useAttention";
import { useIgnoreAttention, useUnignoreAttention } from "@/lib/hooks/useAttentionIgnore";
import { sortAttention } from "@/lib/overview/attention";
import { formatClock } from "@/lib/overview/time";
import { cn } from "@/lib/utils";
import { NEEDS_YOU_CELL, NEEDS_YOU_ROW_GRID, NeedsYouRow } from "./NeedsYouRow";

const LIST = "divide-y divide-border-subtle rounded-xl border border-border bg-surface-raised";
// A long list scrolls inside its own window (about five rows) instead of pushing the
// rest of the Overview down; the header and the ignored line stay in view.
const SCROLL = "max-h-[23rem] overflow-y-auto overscroll-contain";

const rowKey = (item: AttentionItem, i: number) =>
  `${item.kind}:${item.uid ?? ""}:${item.reason_code}:${i}`;

export function NeedsYouList() {
  const { t } = useTranslation();
  const attention = useAttention();
  // An agent's pages are addressed by its type, which an item does not carry.
  const agents = useAgents();
  const agentType = (item: AttentionItem) =>
    item.kind === "agent" ? agents.data?.find((a) => a.uid === item.uid)?.type : undefined;
  const ignore = useIgnoreAttention();
  const restore = useUnignoreAttention();
  const [showIgnored, setShowIgnored] = useState(false);
  const items = attention.data ? sortAttention(attention.data.items) : [];
  const hidden = attention.data ? sortAttention(attention.data.ignored ?? []) : [];
  const errors = attention.data?.errors ?? [];

  return (
    <Section
      as="h2"
      gap="snug"
      labelled
      title={t("overview.needsYou.title")}
      help={items.length > 0 ? t("overview.needsYou.order") : undefined}
    >
      {attention.isPending ? (
        <ul aria-busy className={LIST}>
          {[0, 1, 2].map((i) => (
            <li key={i} className={NEEDS_YOU_ROW_GRID}>
              <Skeleton className="size-2 rounded-full" />
              <Skeleton className={cn(NEEDS_YOU_CELL, "h-2.5 w-32")} />
              <Skeleton className={cn(NEEDS_YOU_CELL, "h-2.5 w-full")} />
            </li>
          ))}
        </ul>
      ) : attention.isError ? (
        <div className="rounded-xl border border-border bg-surface-raised">
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
            <ul className={cn(LIST, SCROLL)} data-testid="needs-you-scroll" tabIndex={0}>
              {items.map((item, i) => (
                <NeedsYouRow
                  key={rowKey(item, i)}
                  item={item}
                  agentType={agentType(item)}
                  onIgnore={() => ignore.mutate(item.key)}
                />
              ))}
            </ul>
          ) : errors.length === 0 ? (
            <AllGood checkedAt={attention.dataUpdatedAt} />
          ) : null}
          {hidden.length > 0 ? (
            <IgnoredLine
              count={hidden.length}
              shown={showIgnored}
              onToggle={() => setShowIgnored((v) => !v)}
            />
          ) : null}
          {hidden.length > 0 && showIgnored ? (
            <ul aria-label={t("overview.needsYou.ignoredList")} className={cn(LIST, SCROLL)}>
              {hidden.map((item, i) => (
                <NeedsYouRow
                  key={rowKey(item, i)}
                  item={item}
                  agentType={agentType(item)}
                  ignored
                  onRestore={() => restore.mutate(item.key)}
                />
              ))}
            </ul>
          ) : null}
        </>
      )}
    </Section>
  );
}

function IgnoredLine({
  count,
  shown,
  onToggle,
}: {
  count: number;
  shown: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <p className="flex justify-end px-1 pt-0.5 text-xs text-text-subtle">
      {t("overview.needsYou.ignored", { count })}
      {" · "}
      <button
        type="button"
        aria-expanded={shown}
        onClick={onToggle}
        className="ml-1 rounded-xs font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
      >
        {shown ? t("overview.needsYou.hideIgnored") : t("overview.needsYou.showIgnored")}
      </button>
    </p>
  );
}

function AllGood({ checkedAt }: { checkedAt: number }) {
  const { t } = useTranslation();
  const iso = checkedAt > 0 ? new Date(checkedAt).toISOString() : null;
  return (
    <div className="flex items-center gap-[14px] rounded-xl border border-border bg-surface-raised px-[18px] py-4">
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
        <Check className="size-4" strokeWidth={2} aria-hidden />
      </span>
      <div className="flex min-w-0 flex-col gap-0.5">
        <p className="text-sm font-semibold text-text">{t("overview.needsYou.empty.title")}</p>
        <p className="text-xs text-text-muted">{t("overview.needsYou.empty.body")}</p>
      </div>
      {iso ? (
        <p className="ml-auto whitespace-nowrap text-xs text-text-subtle">
          {t("overview.needsYou.empty.checked")} <time dateTime={iso}>{formatClock(iso)}</time>
        </p>
      ) : null}
    </div>
  );
}
