// src/components/overview/NeedsYouRow.tsx — one "Needs you" row: what, why, since when, and the one thing to do.
//
// A dot, the item's name (a link to its page) over its kind, the daemon's
// reason as one sentence, when it started, and exactly one action opening the
// page — or the tab — where the person deals with it: a missing secret on
// Secrets, a memory hook changed by hand in the agent's settings on that
// agent's Hooks tab (lib/overview/attention). An item the daemon marks
// `ignorable` — informational, such as an agent simply not connected — also
// carries a ⋯ with Ignore (Stop ignoring once it is ignored). An item whose fix
// is a chore for an agent carries the daemon's hand-off prompt, and its ⋯ then
// offers Copy prompt and, with a managed agent available, Ask an agent — the
// same hand-off the kind's page offers, in the menu because the action column
// has room for one button. Any other row has no menu (Overview boards,
// 1.3.01 / 1.3.05).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { useAgentHandoff } from "@/components/handoff/useAgentHandoff";
import { TruncatedText } from "@/components/ui/truncated-text";
import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { actionPage, itemActionLabelKey, itemPage, severityTone } from "@/lib/overview/attention";
import { useHereOriginState } from "@/lib/origin";
import { kindMeta } from "@/lib/overview/kinds";
import { describeSince } from "@/lib/overview/time";
import { cn } from "@/lib/utils";

/** Dot · name 196 · reason · since 104 · action 176, 14 apart (board 1.3.01). */
const ROW_GRID =
  "grid min-h-[54px] grid-cols-[8px_minmax(0,1fr)] items-center gap-x-[14px] gap-y-1 px-4 py-2 md:grid-cols-[8px_196px_minmax(0,1fr)_104px_176px]";
// On a phone everything after the dot stacks in the second column.
const CELL = "col-start-2 md:col-start-auto";

export const NEEDS_YOU_ROW_GRID = ROW_GRID;
export const NEEDS_YOU_CELL = CELL;

interface Props {
  item: AttentionItem;
  /** The type of the agent an agent item is about — its pages' address. */
  agentType?: string;
  /** Shown under "N ignored · Show": the row is muted and offers Stop ignoring. */
  ignored?: boolean;
  onIgnore?: () => void;
  onRestore?: () => void;
}

export function NeedsYouRow({ item, agentType, ignored = false, onIgnore, onRestore }: Props) {
  const { t } = useTranslation();
  const origin = useHereOriginState();
  const meta = kindMeta(item.kind);
  const KindIcon = meta.icon;
  const since = describeSince(item.since);
  const action = t(itemActionLabelKey(item));
  const run = ignored ? onRestore : onIgnore;
  const handoff = useAgentHandoff(item.handoff?.prompt ?? "");
  const menu: MenuAction[] = [];
  if (item.handoff) {
    menu.push({
      key: "copy-prompt",
      label: t("handoff.copyPrompt"),
      description: t("handoff.copyPromptHint"),
      onSelect: handoff.copy,
    });
    if (handoff.canAsk)
      menu.push({
        key: "ask-agent",
        label: t("handoff.askAgent"),
        description: t("handoff.askAgentHint"),
        onSelect: handoff.ask,
      });
  }
  if (item.ignorable && run) {
    const separated = menu.length > 0;
    menu.push(
      ignored
        ? { key: "restore", label: t("overview.needsYou.restore"), onSelect: run, separated }
        : { key: "ignore", label: t("overview.needsYou.ignore"), onSelect: run, separated },
    );
  }
  return (
    <li className={cn(ROW_GRID, ignored && "opacity-70")}>
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
        state={origin}
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
            state={origin}
            aria-label={t("overview.needsYou.actionFor", { action, name: item.title })}
          >
            {action}
          </Link>
        </Button>
        {menu.length ? (
          <ActionMenu label={t("overview.needsYou.moreFor", { name: item.title })} actions={menu} />
        ) : null}
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
