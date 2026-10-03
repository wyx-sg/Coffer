// src/components/ListPaneStates.tsx — the states a split-view list pane and its right pane show instead of rows.
//
// Boards 1.1.13 (loading), 1.1.14 (load failed) and 1.1.15 (filter matched
// nothing), one pattern for every list page — MCP servers, Skills, CLIs,
// Channels, Custom tools, Model providers, Knowledge:
//   - ListLoadingRows: seven two-line, 52px skeleton rows (title bar, subtitle
//     bar, a pill) so the list keeps the shape of the rows it is about to show.
//   - ListLoadError: inside the list pane, under the page header and the
//     filter, a compact danger block — what failed, that nothing changed, Retry,
//     Open daemon log (Activity › Daemon log) and the failed request in mono.
//   - ListNoMatch: a filter that hid every row, centred in the list pane with
//     a Clear filter button; what the filter searches is the help line.
//   - NothingSelected: the right pane while no row is open, with the page's
//     Add action as an outline button.
// Copy is per kind (`listStates.kinds.<kind>`); no counts appear in any of it.
import { Plus, RotateCcw } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { requestLine, translateApiError } from "@/lib/api/errors";

/** Where "Open daemon log" leads: Activity's Daemon log tab. */
export const DAEMON_LOG_PATH = "/activity?tab=daemon";

/** The kinds a list page names (keys of `listStates.kinds`). */
export type ListKind =
  | "mcp"
  | "skills"
  | "clis"
  | "channels"
  | "customTools"
  | "providers"
  | "knowledge"
  | "memory";

// Title and subtitle bar widths (px) of the seven rows, as drawn on the board.
const ROWS: readonly (readonly [number, number])[] = [
  [90, 150],
  [70, 120],
  [96, 140],
  [64, 110],
  [84, 160],
  [72, 130],
  [88, 120],
];

export function ListLoadingRows() {
  return (
    <div className="flex flex-col gap-px" aria-busy="true">
      {ROWS.map(([title, sub], i) => (
        <div key={i} className="flex h-[52px] items-center gap-2.5 px-2.5">
          <div className="flex min-w-0 grow flex-col gap-[7px]">
            <Skeleton className="h-2.5" style={{ width: title }} />
            <Skeleton className="h-2 bg-surface-sunken/70" style={{ width: sub }} />
          </div>
          <Skeleton className="h-4 w-9" />
        </div>
      ))}
    </div>
  );
}

interface LoadErrorProps {
  kind: ListKind;
  error: unknown;
  onRetry: () => void;
}

export function ListLoadError({ kind, error, onRetry }: LoadErrorProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const reason = translateApiError(t, error).replace(/[.。]$/, "");
  return (
    <EmptyState
      size="compact"
      tone="error"
      className="mx-2 mt-3"
      title={t("listStates.loadFailedTitle", { kinds: t(`listStates.kinds.${kind}.plural`) })}
      description={t("listStates.loadFailedBody", { reason })}
      action={
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RotateCcw aria-hidden /> {t("common.retry")}
        </Button>
      }
      secondaryAction={
        <Button
          size="sm"
          variant="ghost"
          className="text-accent-text"
          onClick={() => navigate(DAEMON_LOG_PATH)}
        >
          {t("listStates.openDaemonLog")}
        </Button>
      }
      detail={requestLine(error) || undefined}
    />
  );
}

interface NoMatchProps {
  kind: ListKind;
  /** What the filter field holds; empty when only a Reach filter hid the rows. */
  query: string;
  onClear: () => void;
}

export function ListNoMatch({ kind, query, onClear }: NoMatchProps) {
  const { t } = useTranslation();
  const noun = t(`listStates.kinds.${kind}.singular`);
  const q = query.trim();
  return (
    <EmptyState
      size="compact"
      title={
        q
          ? t("listStates.noMatch", { kind: noun, query: q })
          : t("listStates.noMatchFilters", { kind: noun })
      }
      description={t(`listStates.kinds.${kind}.filterHelp`)}
      action={
        <Button size="sm" variant="outline" onClick={onClear}>
          {t("listStates.clearFilter")}
        </Button>
      }
    />
  );
}

interface NothingSelectedProps {
  icon: LucideIcon;
  /** The page's Add action, as an outline button. */
  addLabel: string;
  onAdd: () => void;
}

export function NothingSelected({ icon, addLabel, onAdd }: NothingSelectedProps) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={icon}
      title={t("listStates.nothingSelected")}
      description={t("listStates.nothingSelectedBody")}
      action={
        <Button variant="outline" onClick={onAdd}>
          <Plus aria-hidden /> {addLabel}
        </Button>
      }
    />
  );
}
