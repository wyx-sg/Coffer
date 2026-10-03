// src/components/agents/mcp/AgentOwnMcpRows.tsx — the agent's own MCP entries as hairline rows (board 2.1.25).
//
// The name (mono) opens the entry's read-only JSON. Under it: the command or
// URL, the file it sits in, and how many secrets its env holds; a duplicate
// says which Coffer server it duplicates. Right: a state word and one button —
// Adopt, or Remove duplicate. The ⋯ menu holds Remove… only (not on a
// duplicate, whose button does that). A row of a file that failed to parse
// reads Read-only and its actions are disabled.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Dot, KindRow } from "@/components/agents/tabs/KindRow";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { entryCommand, type OwnMcpRow, type OwnMcpState } from "./mcpRows";

const STATE_LABEL: Record<OwnMcpState, string> = {
  bypasses: "agents.mcpTab.state.bypasses",
  duplicate: "agents.mcpTab.state.duplicate",
  readOnly: "agents.mcpTab.state.readOnly",
};

interface Props {
  rows: OwnMcpRow[];
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
            name={
              <button
                type="button"
                onClick={() => onOpenEntry(row)}
                className="max-w-full truncate text-left hover:underline"
              >
                {row.name}
              </button>
            }
            sub={
              <>
                {duplicate !== null ? (
                  <span>
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
                  <span className="truncate font-mono">{entryCommand(entry)}</span>
                )}
                <Dot />
                <span className="font-mono">{whereLabel(entry.source)}</span>
                {duplicate === null && entry.secret_keys.length > 0 ? (
                  <>
                    <Dot />
                    <span>
                      {t("agents.mcpTab.secretsInEnv", { count: entry.secret_keys.length })}
                    </span>
                  </>
                ) : null}
              </>
            }
            trailing={
              <>
                <StatusWord tone={readOnly ? "off" : "warn"}>
                  {t(STATE_LABEL[row.state])}
                </StatusWord>
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
              </>
            }
          />
        );
      })}
    </>
  );
}
