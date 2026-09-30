// src/components/agents/skills/AgentSkillsTable.tsx — the Skills tab's table: Skill · Path · State · Owner · action.
//
// Board 2.1.20. Each row carries the one action its state calls for: Open file
// on Coffer's skills and on an invalid folder, Adopt on the agent's own folder
// (disabled, with the reason, on a foreign link), Remove duplicate on an own
// folder that shares its name with a skill Coffer delivers. A name opens the
// skill's page — the managed skill's own, or the unmanaged folder's read-only
// preview under this tab. The agent's own rows add a ⋯ menu — Adopt, Open
// file, Delete — so a folder that is none of those states can still be deleted.
// Nothing is truncated: paths wrap.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileText, Import, Trash2 } from "lucide-react";

import { DataTable, type Column } from "@/components/DataTable";
import { StatusWord } from "@/components/status/StatusWord";
import { TableActionButton } from "@/components/table/TableActionButton";
import { ActionMenu, type MenuAction } from "@/components/ui/menu";
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

  // The ⋯ menu of the agent's own folder: Adopt · Open file · Delete.
  const ownMenu = (row: OwnSkillRow): MenuAction[] => [
    {
      key: "adopt",
      label: t("agents.skillsTab.menu.adopt"),
      disabled:
        row.item.foreign_link ||
        row.state === "invalid" ||
        row.state === "duplicate" ||
        adoptingKey !== null,
      onSelect: () => onAdopt(row),
    },
    {
      key: "open",
      label: t("agents.skillsTab.openFile"),
      onSelect: () => onOpenFile(skillFilePath(row.item.path)),
    },
    {
      key: "delete",
      label: t("agents.skillsTab.menu.delete"),
      destructive: true,
      separated: true,
      onSelect: () => (row.state === "duplicate" ? onRemoveDuplicate(row) : onDelete(row)),
    },
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
      header: t("agents.skillsTab.cols.skill"),
      cell: (row) => (
        <div className="min-w-0 space-y-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <Link
              to={
                row.owner === "coffer"
                  ? `/skills/${encodeURIComponent(row.name)}`
                  : unmanagedSkillPath(agentType, row.item.location, row.name)
              }
              className="break-all font-medium text-text hover:underline"
            >
              {row.name}
            </Link>
            {row.owner === "coffer" && row.skill.builtin ? (
              <span className="rounded-sm border border-border-subtle px-1.5 text-2xs text-text-muted">
                {t("agents.skillsTab.builtIn")}
              </span>
            ) : null}
          </span>
          {row.description ? <p className="text-xs text-text-muted">{row.description}</p> : null}
        </div>
      ),
    },
    {
      key: "path",
      header: t("agents.skillsTab.cols.path"),
      cell: (row) =>
        row.path ? (
          <span title={row.path} className="break-all font-mono text-xs text-text-muted">
            {abbreviateHomePath(row.path)}
          </span>
        ) : (
          <span className="text-text-muted">{t("common.emptyValue")}</span>
        ),
    },
    {
      key: "state",
      header: t("agents.skillsTab.cols.state"),
      cell: (row) =>
        row.owner === "coffer" ? (
          <StatusWord tone="ok">{t("agents.skillsTab.state.linked")}</StatusWord>
        ) : (
          <div className="space-y-0.5">
            <StatusWord tone={OWN_STATE_TONE[row.state]}>{t(STATE_LABEL[row.state])}</StatusWord>
            {row.stateNote ? <p className="text-xs text-text-muted">{row.stateNote}</p> : null}
          </div>
        ),
    },
    {
      key: "owner",
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
      className: "text-right",
      cell: (row) => {
        if (row.owner === "coffer") {
          const folder = row.path ?? row.skill.master_path;
          return (
            <TableActionButton
              icon={FileText}
              label={t("agents.skillsTab.openFile")}
              aria-label={`${t("agents.skillsTab.openFile")}: ${row.name}`}
              onClick={() => onOpenFile(skillFilePath(folder))}
            />
          );
        }
        if (row.state === "invalid") {
          return withMenu(
            row,
            <TableActionButton
              icon={FileText}
              label={t("agents.skillsTab.openFile")}
              aria-label={`${t("agents.skillsTab.openFile")}: ${row.name}`}
              onClick={() => onOpenFile(skillFilePath(row.item.path))}
            />,
          );
        }
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
      rows={rows}
      columns={columns}
      rowKey={(row) => row.key}
      emptyMessage={t("agents.skillsTab.noMatch")}
    />
  );
}
