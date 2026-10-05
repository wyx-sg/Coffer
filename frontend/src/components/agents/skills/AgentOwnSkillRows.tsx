// src/components/agents/skills/AgentOwnSkillRows.tsx — the agent's own skill folders as table rows (board 2.1.20).
//
// Columns (OWN_SKILL_COLUMNS): Name (mono, opens the folder's read-only page),
// Note (why the state is what it is), Location (the folder it sits in), Status
// (a state word), then at most one button: Adopt on an
// unmanaged folder (hidden — not disabled — on an invalid one or a foreign
// link), Delete duplicate on a folder that shares its name with a skill Coffer
// delivers. The ⋯ menu holds Delete… only, and not on a duplicate, whose
// button already does that.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { RowSelect } from "@/components/agents/tabs/AgentKindTab";
import { KindActions, KindName, KindRow } from "@/components/agents/tabs/KindRow";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { TruncatedText } from "@/components/ui/truncated-text";
import { abbreviateHomePath } from "@/lib/agents/display";
import { unmanagedSkillPath } from "@/lib/agents/routes";
import { OWN_STATE_TONE, skillParentDir, type OwnSkillRow, type OwnSkillState } from "./skillRows";

const STATE_LABEL: Record<OwnSkillState, string> = {
  invalid: "agents.skillsTab.state.invalid",
  foreign: "agents.skillsTab.state.foreign",
  duplicate: "agents.skillsTab.state.duplicate",
  unmanaged: "agents.skillsTab.state.unmanaged",
};

interface Props {
  agentType: string;
  rows: OwnSkillRow[];
  select: RowSelect<OwnSkillRow>;
  onAdopt: (row: OwnSkillRow) => void;
  onDeleteDuplicate: (row: OwnSkillRow) => void;
  /** Delete the agent's own skill folder from disk (asks first). */
  onDelete: (row: OwnSkillRow) => void;
}

export function AgentOwnSkillRows({
  agentType,
  rows,
  select,
  onAdopt,
  onDeleteDuplicate,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  return (
    <>
      {rows.map((row) => {
        const { item } = row;
        const note =
          row.state === "invalid"
            ? (item.reason ?? "")
            : row.state === "foreign"
              ? t("agents.skillsTab.foreignDescription")
              : row.state === "duplicate"
                ? t("agents.skillsTab.duplicateOf", { name: row.name })
                : "";
        return (
          <KindRow
            key={row.key}
            leading={select.leading(row, row.name)}
            openable
            cells={[
              <KindName key="name">
                <Link
                  to={unmanagedSkillPath(agentType, item.location, row.name)}
                  data-row-open
                  className="hover:underline"
                >
                  {row.name}
                </Link>
              </KindName>,
              note ? (
                <TruncatedText
                  key="note"
                  text={note}
                  className={row.state === "invalid" ? "text-danger" : undefined}
                />
              ) : (
                <span key="note" className="text-text-subtle">
                  {t("common.emptyValue")}
                </span>
              ),
              <TruncatedText
                key="location"
                mono
                text={abbreviateHomePath(skillParentDir(item.path))}
              />,
              <StatusWord key="state" tone={OWN_STATE_TONE[row.state]}>
                {t(STATE_LABEL[row.state])}
              </StatusWord>,
              <KindActions key="actions">
                {row.state === "unmanaged" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    aria-label={`${t("agents.skillsTab.adopt")}: ${row.name}`}
                    onClick={() => onAdopt(row)}
                  >
                    {t("agents.skillsTab.adopt")}
                  </Button>
                ) : null}
                {row.state === "duplicate" ? (
                  <Button
                    variant="danger"
                    size="sm"
                    aria-label={`${t("agents.skillsTab.removeDuplicate")}: ${row.name}`}
                    onClick={() => onDeleteDuplicate(row)}
                  >
                    {t("agents.skillsTab.removeDuplicate")}
                  </Button>
                ) : (
                  <ActionMenu
                    label={t("agents.kindTab.moreFor", { name: row.name })}
                    actions={[
                      {
                        key: "delete",
                        label: t("agents.skillsTab.menu.delete"),
                        destructive: true,
                        onSelect: () => onDelete(row),
                      },
                    ]}
                  />
                )}
              </KindActions>,
            ]}
          />
        );
      })}
    </>
  );
}
