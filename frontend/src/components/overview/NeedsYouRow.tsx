// src/components/overview/NeedsYouRow.tsx — one "Needs you" row: what, why, since when, and the one thing to do.
//
// A dot, the item's name (a link to its page) over its kind, the daemon's
// reason as one sentence, when it started, and exactly one action opening the
// page — or the tab — where the person deals with it: a missing secret on
// Secrets, a memory hook changed by hand in the agent's settings on that
// agent's Hooks tab (lib/overview/attention). Every row carries a ⋯ — Copy prompt and, with a managed agent available, Ask
// an agent (the daemon gives every item a hand-off prompt), then Ignore, which
// takes the item off the Overview, the sidebar badges and the menu-bar count
// whatever its severity (Overview boards 1.2.01 / 1.2.09). The button reads
// what it does for that kind and reason ("Reconnect channel", "Review held
// changes", lib/overview/attention itemActionLabelKey) behind a 14px icon for
// its verb; the reason may wrap to two lines, the full text on hover; the row
// takes the hover surface; the ⋯ menu items carry 15px icons.
//
// The action runs in place when it is a non-GET call into Coffer's own state
// that needs no preview — testing an MCP server again, probing a command
// again (lib/overview/attention inPlaceVerb). Then the button reads
// "Retrying…" (disabled) and the reason carries an accent sub-line, "Starting
// <name>… it leaves this list once it answers", until the list has refetched
// (board 1.2.09). Connecting an agent, repairing its config, adding a secret
// and every other verb keep their link: those write outside Coffer's own
// state or need input, and their page holds the preview.
import { Copy, EyeOff, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAgentHandoff } from "@/components/handoff/useAgentHandoff";
import { TruncatedText } from "@/components/ui/truncated-text";
import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import {
  actionIcon,
  actionPage,
  inPlaceVerb,
  itemActionLabelKey,
  itemPage,
  severityTone,
} from "@/lib/overview/attention";
import { kindMeta } from "@/lib/overview/kinds";
import { describeSince } from "@/lib/overview/time";
import { cn } from "@/lib/utils";

/** Dot · name 168 · reason · since 96 · action 212, 14 apart (board 1.2.09). */
const ROW_GRID =
  "grid min-h-[54px] grid-cols-[8px_minmax(0,1fr)] items-center gap-x-[14px] gap-y-1 px-4 py-2 transition-colors duration-fast hover:bg-surface-hover md:grid-cols-[8px_168px_minmax(0,1fr)_96px_212px]";
// On a phone everything after the dot stacks in the second column.
const CELL = "col-start-2 md:col-start-auto";

export const NEEDS_YOU_ROW_GRID = ROW_GRID;
export const NEEDS_YOU_CELL = CELL;

interface Props {
  item: AttentionItem;
  /** The type of the agent an agent item is about — its pages' address. */
  agentType?: string;
  onIgnore: () => void;
  /** Runs the item's in-place action (see inPlaceVerb). */
  onRun?: () => void;
  /** The in-place action has been called and the list has not refetched yet. */
  running?: boolean;
}

export function NeedsYouRow({ item, agentType, onIgnore, onRun, running = false }: Props) {
  const { t } = useTranslation();
  const meta = kindMeta(item.kind);
  const KindIcon = meta.icon;
  const since = describeSince(item.since);
  const action = t(itemActionLabelKey(item));
  const verb = inPlaceVerb(item);
  const ActionIcon = actionIcon(item.action.verb);
  const handoff = useAgentHandoff(item.handoff.prompt);
  const menu: MenuAction[] = [
    {
      key: "copy-prompt",
      label: t("handoff.copyPrompt"),
      icon: Copy,
      description: t("handoff.copyPromptHint"),
      onSelect: handoff.copy,
    },
  ];
  if (handoff.canAsk)
    menu.push({
      key: "ask-agent",
      label: t("handoff.askAgent"),
      icon: MessageSquarePlus,
      description: t("handoff.askAgentHint"),
      onSelect: handoff.ask,
    });
  menu.push({
    key: "ignore",
    label: t("overview.needsYou.ignore"),
    icon: EyeOff,
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
          <KindIcon
            className={cn("shrink-0", item.kind === "agent" ? "size-[15px]" : "size-3.5")}
            aria-hidden
          />
          {t(meta.labelKey)}
        </span>
      </Link>
      <div className={cn(CELL, "flex min-w-0 flex-col gap-0.5")}>
        <TruncatedText text={item.reason} lines={2} className="text-sm text-text" />
        {running && verb ? (
          <p className="text-xs text-accent-text">
            {t(`overview.needsYou.doing.${verb}`, { name: item.title })}
          </p>
        ) : null}
      </div>
      <p className={cn(CELL, "whitespace-nowrap text-xs text-text-subtle")}>
        {since ? <SinceText since={since} iso={item.since ?? ""} /> : null}
      </p>
      <div className={cn(CELL, "flex items-center gap-1.5 md:justify-self-end")}>
        {verb && onRun ? (
          <Button
            variant="outline"
            loading={running}
            onClick={onRun}
            aria-label={t("overview.needsYou.actionFor", {
              action: running ? t(`overview.needsYou.pending.${verb}`) : action,
              name: item.title,
            })}
          >
            {ActionIcon ? <ActionIcon aria-hidden /> : null}
            {running ? t(`overview.needsYou.pending.${verb}`) : action}
          </Button>
        ) : (
          <Button asChild variant="outline">
            <Link
              to={actionPage(item, agentType)}
              aria-label={t("overview.needsYou.actionFor", { action, name: item.title })}
            >
              {ActionIcon ? <ActionIcon aria-hidden /> : null}
              {action}
            </Link>
          </Button>
        )}
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
