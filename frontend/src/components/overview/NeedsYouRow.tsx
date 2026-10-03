// src/components/overview/NeedsYouRow.tsx — one "Needs you" row: what, why, since when, and the one thing to do.
//
// A dot, the item's name (a link to its page) over its kind, the daemon's
// reason as one sentence, when it started, and exactly one action opening the
// page — or the tab — where the person deals with it: a missing secret on
// Secrets, a memory hook changed by hand in the agent's settings on that
// agent's Hooks tab (lib/overview/attention). An item the daemon marks
// every row carries a ⋯ — Copy prompt and, with a managed agent available, Ask
// an agent (the daemon gives every item a hand-off prompt), then Ignore, which
// takes the item off the Overview, the sidebar badges and the menu-bar count
// whatever its severity (Overview boards, 1.2.01 / 1.2.02).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAgentHandoff } from "@/components/handoff/useAgentHandoff";
import { TruncatedText } from "@/components/ui/truncated-text";
import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { actionPage, itemActionLabelKey, itemPage, severityTone } from "@/lib/overview/attention";
import { kindMeta } from "@/lib/overview/kinds";
import { describeSince } from "@/lib/overview/time";
import { cn } from "@/lib/utils";

/** Dot · name 168 · reason · since 96 · action 212, 14 apart (board 1.2.09). */
const ROW_GRID =
  "grid min-h-[54px] grid-cols-[8px_minmax(0,1fr)] items-center gap-x-[14px] gap-y-1 px-4 py-2 md:grid-cols-[8px_168px_minmax(0,1fr)_96px_212px]";
// On a phone everything after the dot stacks in the second column.
const CELL = "col-start-2 md:col-start-auto";

export const NEEDS_YOU_ROW_GRID = ROW_GRID;
export const NEEDS_YOU_CELL = CELL;

interface Props {
  item: AttentionItem;
  /** The type of the agent an agent item is about — its pages' address. */
  agentType?: string;
  onIgnore: () => void;
}

export function NeedsYouRow({ item, agentType, onIgnore }: Props) {
  const { t } = useTranslation();
  const meta = kindMeta(item.kind);
  const KindIcon = meta.icon;
  const since = describeSince(item.since);
  const action = t(itemActionLabelKey(item));
  const handoff = useAgentHandoff(item.handoff.prompt);
  const menu: MenuAction[] = [
    {
      key: "copy-prompt",
      label: t("handoff.copyPrompt"),
      description: t("handoff.copyPromptHint"),
      onSelect: handoff.copy,
    },
  ];
  if (handoff.canAsk)
    menu.push({
      key: "ask-agent",
      label: t("handoff.askAgent"),
      description: t("handoff.askAgentHint"),
      onSelect: handoff.ask,
    });
  menu.push({
    key: "ignore",
    label: t("overview.needsYou.ignore"),
    onSelect: onIgnore,
    separated: true,
  });
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
      <Link
        to={itemPage(item, agentType)}
        className={cn(CELL, "group flex min-w-0 flex-col gap-0.5")}
      >
        <span
          className={cn(
            "block truncate text-text group-hover:underline",
            meta.identifier ? "font-mono text-xs font-medium" : "text-sm font-label",
          )}
        >
          {item.title}
        </span>
        <span className="flex items-center gap-1.5 text-2xs text-text-subtle">
          <KindIcon className="size-3" aria-hidden />
          {t(meta.labelKey)}
        </span>
      </Link>
      <TruncatedText text={item.reason} className={cn(CELL, "min-w-0 text-sm text-text")} />
      <p className={cn(CELL, "whitespace-nowrap text-xs text-text-subtle")}>
        {since ? <SinceText since={since} iso={item.since ?? ""} /> : null}
      </p>
      <div className={cn(CELL, "flex items-center gap-1.5 md:justify-self-end")}>
        <Button asChild variant="outline">
          <Link
            to={actionPage(item, agentType)}
            aria-label={t("overview.needsYou.actionFor", { action, name: item.title })}
          >
            {action}
          </Link>
        </Button>
        <ActionMenu label={t("overview.needsYou.moreFor", { name: item.title })} actions={menu} />
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
