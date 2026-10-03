// src/components/overview/NeedsYouList.tsx — "Needs you": one row per problem across every area, most urgent first.
//
// Rows are NeedsYouRow. They clear themselves: an attention change on the
// event stream refetches the list (useDaemonEvents). A source that could not
// be checked says so above the rows, so a short list is never mistaken for a
// complete one. Items ignored on this machine (an agent left unconnected on
// purpose) leave the daemon's `items`, and with them the Overview, the counts
// the sidebar and the menu bar read; no ignored list is shown here. A list
// longer than about six rows scrolls inside its frame under the title, behind
// a thin overlay thumb. A source that failed is one muted status line, its
// icon red (Overview board 1.2.04). With nothing left, the list is the calm
// "Nothing needs you" card (AllGoodCard, board 1.2.03).
import { AlertTriangle, CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAgents } from "@/lib/hooks/useAgents";
import { useAttention, type AttentionItem } from "@/lib/hooks/useAttention";
import { useIgnoreAttention } from "@/lib/hooks/useAttentionIgnore";
import { useInPlaceActions } from "@/lib/hooks/useInPlaceAction";
import { sortAttention } from "@/lib/overview/attention";
import { cn } from "@/lib/utils";
import { AllGoodCard } from "./AllGoodCard";
import { NEEDS_YOU_CELL, NEEDS_YOU_ROW_GRID, NeedsYouRow } from "./NeedsYouRow";

const LIST = "divide-y divide-border-subtle rounded-xl border border-border bg-surface-raised";
// A long list scrolls inside its own window (368px, about six rows) instead of pushing
// the rest of the Overview down; the section title stays in view.
const SCROLL = "scroll-overlay max-h-[368px] overflow-y-auto overscroll-contain";

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
  const inPlace = useInPlaceActions();
  const items = attention.data ? sortAttention(attention.data.items) : [];
  const errors = attention.data?.errors ?? [];

  return (
    <Section
      as="h2"
      gap="snug"
      compact
      labelled
      title={t("overview.needsYou.title")}
      aside={
        items.length > 0 ? (
          <span
            data-testid="needs-you-count"
            className="inline-flex h-5 items-center rounded-[5px] bg-surface-sunken px-[7px] text-2xs font-label text-text-muted"
          >
            {items.length}
          </span>
        ) : null
      }
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
            <p
              key={e.source}
              role="status"
              className="flex items-center gap-2 text-xs text-text-muted"
            >
              <CircleAlert className="size-3.5 shrink-0 text-danger" aria-hidden />
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
                  onRun={() => void inPlace.run(item)}
                  running={inPlace.running.has(item.key)}
                />
              ))}
            </ul>
          ) : errors.length === 0 ? (
            <AllGoodCard checkedAt={attention.dataUpdatedAt} />
          ) : null}
        </>
      )}
    </Section>
  );
}
