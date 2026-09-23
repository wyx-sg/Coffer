// frontend/src/components/workflow/RunContextColumns.tsx
// The columns of the run's context table, kept apart from RunContext.tsx so
// that file stays within its size budget.
//
// The columns are where the two halves of the table meet: every one of them
// has to say something true of a mounted input AND of a produced artifact, or
// say nothing at all. "Where" is blank when it would only repeat the name,
// "Size" is an em dash for the kinds that have no bytes, and the unmount
// button exists only on the rows it could mean anything for.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  BookOpen,
  ExternalLink,
  FileText,
  FolderOpen,
  GitBranch,
  Link2,
  NotebookPen,
  Package,
  X,
} from "lucide-react";

import { type Column } from "@/components/DataTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatBytes, formatDateTime } from "@/lib/utils";
import { fsApi } from "@/lib/api/fs";
import type { ContextKind, ContextRow } from "@/lib/workflow/contextRows";

const ICONS: Record<ContextKind, typeof BookOpen> = {
  knowledge: BookOpen,
  file: FileText,
  note: NotebookPen,
  link: Link2,
  repo: GitBranch,
  artifact: Package,
};

interface Args {
  /** The run these rows belong to, for the file page's link. */
  runId: string;
  /** False when another machine advances this run. */
  ownedHere: boolean;
  /** Display name of the owning machine, for the read-only tooltip. */
  machine: string;
  /** True while an unmount is in flight, which disables every unmount. */
  removing: boolean;
  onRemove: (row: ContextRow) => void;
}

/** The name cell: a link, an anchor, a button or plain text, by what the row
 *  opens. Whatever it is, it looks the same and reads the same. */
const NAME_CLASS =
  "rounded-sm text-left font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function useRunContextColumns({
  runId,
  ownedHere,
  machine,
  removing,
  onRemove,
}: Args): Column<ContextRow>[] {
  const { t } = useTranslation();

  const name = (row: ContextRow) => {
    const open = row.open;
    if (open === null) return <span className="font-medium">{row.name}</span>;
    if (open.how === "collection") {
      return (
        <Link className={NAME_CLASS} to={`/knowledge/${encodeURIComponent(open.name)}`}>
          {row.name}
        </Link>
      );
    }
    if (open.how === "url") {
      return (
        <a
          className={`${NAME_CLASS} inline-flex items-center gap-1`}
          href={open.href}
          target="_blank"
          // `noreferrer` as well as `noopener`: the URL is one the developer
          // mounted, but the page behind it is not this vault's.
          rel="noreferrer noopener"
        >
          {row.name}
          <ExternalLink className="size-3 shrink-0 opacity-60" aria-hidden />
        </a>
      );
    }
    if (open.how === "note") {
      return (
        <Link
          className={NAME_CLASS}
          to={`/runs/${encodeURIComponent(runId)}/notes/${encodeURIComponent(open.ref)}`}
        >
          {row.name}
        </Link>
      );
    }
    if (open.how === "reveal") {
      return (
        <button
          type="button"
          className={`${NAME_CLASS} inline-flex items-center gap-1`}
          title={t("workflow.context.reveal")}
          // A checkout is a directory; there is nothing to preview and the
          // file manager is where a developer wants a directory anyway.
          onClick={() => void fsApi.reveal(open.path).catch(() => {})}
        >
          {row.name}
          <FolderOpen className="size-3 shrink-0 opacity-60" aria-hidden />
        </button>
      );
    }
    return (
      <Link
        className={NAME_CLASS}
        to={`/runs/${encodeURIComponent(runId)}/files?path=${encodeURIComponent(open.path)}`}
      >
        {row.name}
      </Link>
    );
  };

  return [
    {
      key: "kind",
      header: t("workflow.context.cols.kind"),
      className: "whitespace-nowrap",
      cell: (row) => {
        const Icon = ICONS[row.kind];
        return (
          <span className="flex items-center gap-2">
            <Icon className="size-4 text-muted-foreground" aria-hidden />
            {/* A recognised link says WHAT it is — Confluence, Jira — rather
                than "Link", because that is the thing a reader is scanning
                for and it is the same word the node was told. */}
            <Badge variant="outline">
              {row.kind === "artifact"
                ? t("workflow.context.artifact")
                : row.provider !== null
                  ? t(`workflow.inputs.providers.${row.provider}`, { defaultValue: row.provider })
                  : t(`workflow.inputs.kinds.${row.kind}`)}
            </Badge>
          </span>
        );
      },
    },
    {
      key: "name",
      header: t("workflow.context.cols.name"),
      cell: name,
    },
    {
      key: "where",
      header: t("workflow.context.cols.where"),
      // `max-w-0` with `w-full` is what makes the truncation below bite: a
      // table cell sizes to its content otherwise, and a mounted repository's
      // absolute path is long enough to push the columns after it off the
      // right edge. One line each, and the full path on hover.
      className: "w-full max-w-0",
      cell: (row) =>
        row.where === null ? null : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="block truncate font-mono text-xs text-muted-foreground">
                {row.where}
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-lg break-all font-mono text-xs">
              {row.where}
            </TooltipContent>
          </Tooltip>
        ),
    },
    {
      key: "size",
      // Size is a file's alone — a link and a collection have no bytes to
      // report, and inventing a number would be a lie about them.
      header: t("workflow.context.cols.size"),
      className: "whitespace-nowrap text-right",
      cell: (row) => (
        <span className="text-muted-foreground">
          {row.size == null ? "—" : formatBytes(row.size)}
        </span>
      ),
    },
    {
      key: "origin",
      header: t("workflow.context.cols.origin"),
      className: "whitespace-nowrap",
      cell: (row) =>
        row.produced === null ? (
          <span className="text-muted-foreground">{t("workflow.context.added")}</span>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-muted-foreground">
                {t("workflow.context.producedBy", {
                  node: row.produced.nodeKey,
                  attempt: t("workflow.node.attempt", { count: row.produced.attempt }),
                })}
              </span>
            </TooltipTrigger>
            <TooltipContent>{formatDateTime(row.produced.at)}</TooltipContent>
          </Tooltip>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "whitespace-nowrap text-right",
      // Only a mounted input can be unmounted. An artifact is a file a task
      // wrote, and the catalogue is generated from what is on disk —
      // there is nothing here for a delete button to mean.
      // Icon AND word. An × alone is only unambiguous to someone who already
      // knows what this column does, and "remove" has more than one plausible
      // meaning here — the row, the file, the collection it points at.
      cell: (row) =>
        row.input === null ? null : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className={ownedHere ? undefined : "cursor-not-allowed"}>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={!ownedHere || removing}
                  onClick={() => onRemove(row)}
                >
                  <X aria-hidden />
                  {t("workflow.inputs.remove")}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {ownedHere
                ? t("workflow.inputs.removeHint")
                : t("workflow.notThisMachine", { machine })}
            </TooltipContent>
          </Tooltip>
        ),
    },
  ];
}
