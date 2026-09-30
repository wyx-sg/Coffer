// src/components/overview/NeedsYouRow.tsx — one "Needs you" row: what, why, since when, and the one thing to do.
//
// A dot, the item's name (a link to its page) over its kind, the daemon's
// reason as one sentence, when it started, and exactly one action opening the
// page — or the tab — where the person deals with it: a missing secret on
// Secrets, a memory hook changed by hand in the agent's settings on that
// agent's Hooks tab (lib/overview/attention). An item the daemon marks
// `ignorable` — informational, such as an agent simply not connected — also
// carries a ⋯ with Ignore (Stop ignoring once it is ignored); no other row
// has a menu (Overview boards, 1.3.01 / 1.3.05).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { StatusDot } from "@/components/status/StatusDot";
import { Button } from "@/components/ui/button";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import type { AttentionItem } from "@/lib/hooks/useAttention";
import { actionPage, itemActionLabelKey, itemPage, severityTone } from "@/lib/overview/attention";
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
  /** Shown under "N ignored · Show": the row is muted and offers Stop ignoring. */
  ignored?: boolean;
  onIgnore?: () => void;
  onRestore?: () => void;
}

export function NeedsYouRow({ item, ignored = false, onIgnore, onRestore }: Props) {
  const { t } = useTranslation();
  const meta = kindMeta(item.kind);
  const KindIcon = meta.icon;
  const since = describeSince(item.since);
  const action = t(itemActionLabelKey(item));
  const run = ignored ? onRestore : onIgnore;
  const menu: MenuAction | null =
    item.ignorable && run
      ? ignored
        ? { key: "restore", label: t("overview.needsYou.restore"), onSelect: run }
        : { key: "ignore", label: t("overview.needsYou.ignore"), onSelect: run }
      : null;
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
      <Link to={itemPage(item)} className={cn(CELL, "group flex min-w-0 flex-col gap-0.5")}>
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
      <p className={cn(CELL, "min-w-0 text-sm text-text")}>{item.reason}</p>
      <p className={cn(CELL, "whitespace-nowrap text-xs text-text-subtle")}>
        {since ? <SinceText since={since} iso={item.since ?? ""} /> : null}
      </p>
      <div className={cn(CELL, "flex items-center gap-1.5 md:justify-self-end")}>
        <Button asChild variant="outline">
          <Link
            to={actionPage(item)}
            aria-label={t("overview.needsYou.actionFor", { action, name: item.title })}
          >
            {action}
          </Link>
        </Button>
        {menu ? (
          <ActionMenu
            label={t("overview.needsYou.moreFor", { name: item.title })}
            actions={[menu]}
          />
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
