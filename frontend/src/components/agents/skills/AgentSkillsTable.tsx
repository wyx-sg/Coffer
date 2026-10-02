// src/components/agents/skills/AgentSkillsTable.tsx — the Skills tab's table: Skill · Path · State · Owner · action.
//
// Board 2.1.20. Each row carries the one action its state calls for: Open file
// on Coffer's skills and on an invalid folder, Adopt on the agent's own folder
// (disabled, with the reason, on a foreign link), Remove duplicate on an own
// folder that shares its name with a skill Coffer delivers. A name opens the
// skill's page — the managed skill's own, or the unmanaged folder's read-only
// preview under this tab. The agent's own rows add a ⋯ menu — Open file, Delete
// (no Delete on a duplicate: its button already removes it).
// Fixed layout, one line per cell: name, description, path and state note end
// in an ellipsis with the full text in a tooltip, so every row is one height.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Import, Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
import { TruncatedPath, TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import { unmanagedSkillPath } from "@/lib/agents/routes";
import {
  OWN_STATE_TONE,
  skillFilePath,
  type OwnSkillRow,
  type OwnSkillState,
  type SkillRow,
} from "./skillRows";

const STATE_LABEL: Record<OwnSkillState, string> = {
  notManaged: "agents.skillsTab.state.notManaged",
  foreign: "agents.skillsTab.foreignLink",
  invalid: "agents.skillsTab.state.invalid",
  duplicate: "agents.skillsTab.state.duplicate",
  adoptFailed: "agents.skillsTab.state.adoptFailed",
};

interface Props {
  agentType: string;
  rows: SkillRow[];
  /** The row whose adoption is in flight, if any. */
  adoptingKey: string | null;
  onAdopt: (row: OwnSkillRow) => void;
  onRemoveDuplicate: (row: OwnSkillRow) => void;
  onOpenFile: (path: string) => void;
  /** Delete the agent's own skill folder from disk (asks first). */
  onDelete: (row: OwnSkillRow) => void;
}

export function AgentSkillsTable({
  agentType,
  rows,
  adoptingKey,
  onAdopt,
  onRemoveDuplicate,
  onOpenFile,
  onDelete,
}: Props) {
  const { t } = useTranslation();

  // The ⋯ menu of the agent's own folder: Open file · Delete. Adopt and Remove
  // duplicate are the row's visible button (and where the row has no button,
  // Adopt could not run anyway), so the menu does not repeat them.
  const ownMenu = (row: OwnSkillRow): MenuAction[] => [
    {
      key: "open",
      label: t("agents.skillsTab.openFile"),
      onSelect: () => onOpenFile(skillFilePath(row.item.path)),
    },
    ...(row.state === "duplicate"
      ? []
      : [
          {
            key: "delete",
            label: t("agents.skillsTab.menu.delete"),
            destructive: true,
            separated: true,
            onSelect: () => onDelete(row),
          },
        ]),
  ];
  const withMenu = (row: OwnSkillRow, action: ReactNode) => (
    <span className="inline-flex items-center justify-end gap-1">
      {action}
      <ActionMenu label={t("agents.kindTab.moreFor", { name: row.name })} actions={ownMenu(row)} />
    </span>
  );

  const columns: Column<SkillRow>[] = [
    {
      key: "skill",
      className: "w-[34%]",
      header: t("agents.skillsTab.cols.skill"),
      cell: (row) => (
        <div className="min-w-0 space-y-0.5">
          <span className="flex min-w-0 items-center gap-2">
            <Link
              to={
                row.owner === "coffer"
                  ? `/skills/${encodeURIComponent(row.name)}`
                  : unmanagedSkillPath(agentType, row.item.location, row.name)
              }
              className="min-w-0 font-medium text-text hover:underline"
            >
              <TruncatedText text={row.name} />
            </Link>
            {row.owner === "coffer" && row.skill.builtin ? (
              <span className="shrink-0 rounded-sm border border-border-subtle px-1.5 text-2xs text-text-muted">
                {t("agents.skillsTab.builtIn")}
              </span>
            ) : null}
          </span>
          {row.description ? (
            <TruncatedText text={row.description} className="text-xs text-text-muted" />
          ) : null}
        </div>
      ),
    },
    {
      key: "path",
      header: t("agents.skillsTab.cols.path"),
      cell: (row) =>
        row.path ? (
          <TruncatedPath text={abbreviateHomePath(row.path)} className="text-xs text-text-muted" />
        ) : (
          <span className="text-text-muted">{t("common.emptyValue")}</span>
        ),
    },
    {
      key: "state",
      className: "w-[150px]",
      header: t("agents.skillsTab.cols.state"),
      cell: (row) =>
        row.owner === "coffer" ? (
          <StatusWord tone="ok">{t("agents.skillsTab.state.linked")}</StatusWord>
        ) : (
          <div className="min-w-0 space-y-0.5">
            <StatusWord tone={OWN_STATE_TONE[row.state]}>{t(STATE_LABEL[row.state])}</StatusWord>
            {row.stateNote ? (
              <TruncatedText text={row.stateNote} className="text-xs text-text-muted" />
            ) : null}
          </div>
        ),
    },
    {
      key: "owner",
      className: "w-[84px]",
      header: t("agents.skillsTab.cols.owner"),
      cell: (row) => (
        <span className="whitespace-nowrap text-xs text-text-muted">
          {t(`agents.kindTab.owner.${row.owner}`)}
        </span>
      ),
    },
    {
      key: "actions",
      header: <span className="sr-only">{t("agents.skillsTab.cols.actions")}</span>,
      className: "w-[210px] text-right",
      cell: (row) => {
        // A Coffer-managed skill has nothing to act on here: its name opens its page,
        // where the file is read and opened.
        if (row.owner === "coffer") return null;
        // An invalid one has only the ⋯ menu (its Open file lives there).
        if (row.state === "invalid") return withMenu(row, null);
        if (row.state === "duplicate") {
          return withMenu(
            row,
            <TableActionButton
              icon={Trash2}
              destructive
              label={t("agents.skillsTab.removeDuplicate")}
              aria-label={`${t("agents.skillsTab.removeDuplicate")}: ${row.name}`}
              onClick={() => onRemoveDuplicate(row)}
            />,
          );
        }
        const foreign = row.item.foreign_link;
        return withMenu(
          row,
          // The wrapper carries the reason: a disabled button fires no pointer events.
          <span title={foreign ? t("agents.skillsTab.adoptDisabledForeign") : undefined}>
            <TableActionButton
              icon={Import}
              label={t("agents.skillsTab.adopt")}
              aria-label={`${t("agents.skillsTab.adopt")}: ${row.name}`}
              disabled={foreign || adoptingKey !== null}
              onClick={() => onAdopt(row)}
            />
          </span>,
        );
      },
    },
  ];

  return (
    <DataTable
      fixed
      rows={rows}
      columns={columns}
      rowKey={(row) => row.key}
      emptyMessage={t("agents.skillsTab.noMatch")}
    />
  );
}
