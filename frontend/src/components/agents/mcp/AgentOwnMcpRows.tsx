// src/components/agents/mcp/AgentOwnMcpRows.tsx — the agent's own MCP entries as table rows (board 2.1.25).
//
// Columns (ownMcpColumns): Name (mono, opens the entry's read-only JSON),
// Command (the command or URL and how many secrets its env holds; a duplicate
// says which Coffer server it duplicates), File (where it sits), Status (a state
// word), then one button —
// Adopt, or Remove duplicate. The ⋯ menu holds Remove… only (not on a
// duplicate, whose button does that). A row of a file that failed to parse
// reads Read-only and its actions are disabled.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { RowSelect } from "@/components/agents/tabs/AgentKindTab";
import { KindActions, KindName, KindRow } from "@/components/agents/tabs/KindRow";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { TruncatedText } from "@/components/ui/truncated-text";
import { entryCommand, type OwnMcpRow, type OwnMcpState } from "./mcpRows";

const STATE_LABEL: Record<OwnMcpState, string> = {
  bypasses: "agents.mcpTab.state.bypasses",
  duplicate: "agents.mcpTab.state.duplicate",
  readOnly: "agents.mcpTab.state.readOnly",
};

interface Props {
  rows: OwnMcpRow[];
  select: RowSelect<OwnMcpRow>;
  /** The file a direct entry sits in, home-relative. */
  whereLabel: (source: string) => string;
  onAdopt: (row: OwnMcpRow) => void;
  onRemoveDuplicate: (row: OwnMcpRow) => void;
  onRemove: (row: OwnMcpRow) => void;
  /** A direct entry's name: its JSON opens in a dialog. */
  onOpenEntry: (row: OwnMcpRow) => void;
}

export function AgentOwnMcpRows({
  rows,
  select,
  whereLabel,
  onAdopt,
  onRemoveDuplicate,
  onRemove,
  onOpenEntry,
}: Props) {
  const { t } = useTranslation();
  return (
    <>
      {rows.map((row) => {
        const { entry } = row;
        const readOnly = row.state === "readOnly";
        const duplicate = entry.matches_resource;
        return (
          <KindRow
            key={row.key}
            leading={select.leading(row, row.name)}
            cells={[
              <KindName key="name">
                <button
                  type="button"
                  onClick={() => onOpenEntry(row)}
                  className="max-w-full truncate text-left hover:underline"
                >
                  {row.name}
                </button>
              </KindName>,
              duplicate !== null ? (
                <span key="command" className="block truncate">
                  {t("agents.mcpTab.duplicateOfLead")}{" "}
                  <Link
                    to={`/mcp-servers/${encodeURIComponent(duplicate)}`}
                    className="font-mono text-accent-text hover:underline"
                  >
                    {duplicate}
                  </Link>{" "}
                  {t("agents.mcpTab.duplicateOfTail")}
                </span>
              ) : (
                <span key="command" className="flex min-w-0 items-center gap-1.5">
                  <TruncatedText mono text={entryCommand(entry)} className="min-w-0" />
                  {entry.secret_keys.length > 0 ? (
                    <span className="shrink-0 text-text-subtle">
                      {t("agents.mcpTab.secretsInEnv", { count: entry.secret_keys.length })}
                    </span>
                  ) : null}
                </span>
              ),
              <TruncatedText key="file" mono text={whereLabel(entry.source)} />,
              <StatusWord key="state" tone={readOnly ? "off" : "warn"}>
                {t(STATE_LABEL[row.state])}
              </StatusWord>,
              <KindActions key="actions">
                {duplicate !== null ? (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={readOnly}
                    aria-label={`${t("agents.mcpTab.removeDuplicate")}: ${row.name}`}
                    onClick={() => onRemoveDuplicate(row)}
                  >
                    {t("agents.mcpTab.removeDuplicate")}
                  </Button>
                ) : (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={readOnly}
                      aria-label={`${t("agents.mcpTab.adopt")}: ${row.name}`}
                      onClick={() => onAdopt(row)}
                    >
                      {t("agents.mcpTab.adopt")}
                    </Button>
                    <ActionMenu
                      label={t("agents.kindTab.moreFor", { name: row.name })}
                      actions={[
                        {
                          key: "remove",
                          label: t("agents.mcpTab.menu.remove"),
                          destructive: true,
                          disabled: readOnly,
                          onSelect: () => onRemove(row),
                        },
                      ]}
                    />
                  </>
                )}
              </KindActions>,
            ]}
          />
        );
      })}
    </>
  );
}
