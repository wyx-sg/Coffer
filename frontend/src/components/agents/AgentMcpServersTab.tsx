// src/components/agents/AgentMcpServersTab.tsx — the agent's MCP servers tab: Coffer's gateway servers and its direct entries, in one table.
//
// Board 2.1.23, spec agent-registry "Filter an agent's installed kinds by
// owner". Coffer's rows are the registered MCP servers that reach this agent
// through the gateway; Connected means the agent's Coffer connection carries
// the gateway entry. The agent's own rows are the direct entries in its config
// files ("List the MCP entries in the agent's own config files"): Adopt moves
// one into Coffer (AgentAdoptMcpDialog), and Remove duplicate takes out an
// entry Coffer's gateway already serves, so the tab then lists the server once,
// as Coffer's. Each direct entry's ⋯ menu (board 2.1.54) adds opening its file,
// copying its command and removing it from the file. A config file that fails
// to parse is named above the table and its entries stay read-only.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Server } from "lucide-react";

import { AgentAdoptMcpDialog } from "@/components/agents/AgentAdoptMcpDialog";
import { AgentMcpTable } from "@/components/agents/mcp/AgentMcpTable";
import { McpParseErrorAlert } from "@/components/agents/mcp/McpParseErrorAlert";
import {
  buildMcpRows,
  entryCommand,
  singleSource,
  type OwnMcpRow,
} from "@/components/agents/mcp/mcpRows";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import type { MenuAction } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import { useFsActions } from "@/lib/fsActions";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { countByOwner } from "@/lib/agents/owner";
import type { AgentOut } from "@/lib/api/agents";
import {
  useAgentConfigFiles,
  useAgentConnection,
  useAgentMcpEntries,
  useRemoveMcpEntry,
} from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";

export function AgentMcpServersTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const servers = useResources("mcp_server");
  const entries = useAgentMcpEntries(agent.uid);
  const connection = useAgentConnection(agent.uid);
  const configFiles = useAgentConfigFiles(agent.uid);
  const removeEntry = useRemoveMcpEntry(agent.uid);
  const [adoptTarget, setAdoptTarget] = useState<OwnMcpRow | null>(null);
  const [removeTarget, setRemoveTarget] = useState<OwnMcpRow | null>(null);
  const agentLabel = agentTypeLabel(agent.type);

  const parseErrors = useMemo(() => entries.data?.parse_errors ?? [], [entries.data]);
  const rows = useMemo(
    () =>
      buildMcpRows(
        agent.uid,
        servers.data ?? [],
        entries.data?.items ?? [],
        new Set(parseErrors.map((pe) => pe.source)),
      ),
    [agent.uid, servers.data, entries.data, parseErrors],
  );
  const counts = countByOwner(rows);
  const connected = connection.data
    ? connection.data.parts.some((p) => p.key === "mcp" && p.installed)
    : undefined;

  // A direct entry's file: its absolute path, and home-relative as the Where
  // column shows it (the key itself until the listing is read).
  const pathOf = (source: string) =>
    configFiles.data?.find((f) => f.key === source)?.path ??
    parseErrors.find((pe) => pe.source === source)?.path;
  const whereLabel = (source: string) => {
    const path = pathOf(source);
    return path ? abbreviateHomePath(path) : source;
  };

  const rowMenu = (row: OwnMcpRow): MenuAction[] => {
    const readOnly = row.state === "readOnly";
    const file = whereLabel(row.entry.source);
    const path = pathOf(row.entry.source);
    const command = entryCommand(row.entry);
    return [
      {
        key: "adopt",
        label: t("agents.mcpTab.menu.adopt"),
        disabled: readOnly || row.entry.matches_resource !== null,
        onSelect: () => setAdoptTarget(row),
      },
      {
        key: "open",
        label: t("agents.mcpTab.menu.open", { file }),
        disabled: !path,
        onSelect: () =>
          path &&
          void fs.open(path, "").catch(() => toast.error(t("agents.mcpTab.openFileFailed"))),
      },
      {
        key: "copy",
        label: t("agents.mcpTab.menu.copyCommand"),
        disabled: !command,
        onSelect: () =>
          void navigator.clipboard
            ?.writeText(command)
            .then(() => toast.success(t("common.copied")))
            .catch(() => undefined),
      },
      {
        key: "remove",
        label: t("agents.mcpTab.menu.remove", { file }),
        destructive: true,
        separated: true,
        disabled: readOnly,
        onSelect: () => setRemoveTarget(row),
      },
    ];
  };
  const oneFile = singleSource(rows);
  const summaryFile = oneFile ? whereLabel(oneFile) : t("agents.mcpTab.ownConfig");

  return (
    <>
      <AgentKindTab
        rows={rows}
        summary={t("agents.mcpTab.summary", {
          count: rows.length,
          coffer: counts.coffer,
          own: counts.own,
          file: summaryFile,
        })}
        searchPlaceholder={t("agents.mcpTab.search")}
        searchText={(row) =>
          row.owner === "own"
            ? `${row.name} ${row.entry.command ?? ""} ${row.entry.args.join(" ")} ${row.entry.url ?? ""}`
            : row.name
        }
        isLoading={servers.isPending || entries.isPending}
        error={entries.error ?? servers.error}
        onRetry={() => {
          void servers.refetch();
          void entries.refetch();
        }}
        empty={{
          icon: Server,
          title: t("agents.mcpTab.emptyTitle", { agent: agentLabel }),
          description: t("agents.mcpTab.emptyDescription", { agent: agentLabel }),
        }}
        footnote={t("agents.mcpTab.footnote")}
      >
        {(visible) => (
          <>
            {parseErrors.map((pe) => (
              <McpParseErrorAlert
                key={`${pe.source}:${pe.path}`}
                agentType={agent.type}
                error={pe}
              />
            ))}
            <AgentMcpTable
              agentType={agent.type}
              rows={visible}
              connected={connected}
              whereLabel={whereLabel}
              onAdopt={setAdoptTarget}
              onRemoveDuplicate={setRemoveTarget}
              rowMenu={rowMenu}
            />
          </>
        )}
      </AgentKindTab>

      {adoptTarget ? (
        <AgentAdoptMcpDialog
          agentUid={agent.uid}
          agentName={agent.name}
          agentLabel={agentLabel}
          fileLabel={whereLabel(adoptTarget.entry.source)}
          entry={adoptTarget.entry}
          open
          onOpenChange={(next) => {
            if (!next) setAdoptTarget(null);
          }}
        />
      ) : null}

      <ConfirmDialog
        open={removeTarget !== null}
        onOpenChange={(next) => {
          if (!next) setRemoveTarget(null);
        }}
        title={t("agents.mcpTab.removeTitle", {
          name: removeTarget?.name ?? "",
          file: removeTarget ? whereLabel(removeTarget.entry.source) : "",
        })}
        description={
          removeTarget?.entry.matches_resource
            ? t("agents.mcpTab.removeDuplicateBody", {
                agent: agentLabel,
                name: removeTarget.entry.matches_resource,
              })
            : t("agents.mcpTab.removeBody", { agent: agentLabel })
        }
        confirmLabel={t("agents.mcpTab.remove")}
        pending={removeEntry.isPending}
        onConfirm={() => {
          if (!removeTarget) return;
          removeEntry.mutate(
            { entry: removeTarget.name, source: removeTarget.entry.source },
            { onSuccess: () => setRemoveTarget(null) },
          );
        }}
      />
    </>
  );
}
