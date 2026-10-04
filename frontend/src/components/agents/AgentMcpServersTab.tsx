// src/components/agents/AgentMcpServersTab.tsx — the agent's MCP servers tab: Coffer's part first, then the agent's own entries.
//
// Boards 2.1.25–2.1.30, 2.1.59. "From Coffer" is one row — how many registered
// servers reach this agent through Coffer's one MCP entry and their first
// names — linking to the MCP servers page filtered to this agent, and a second
// for the custom-tool groups, linking to Custom tools. Below them the
// agent's own servers: the direct entries in its config files ("List the MCP
// entries in the agent's own config files"). Adopt moves one into Coffer
// (AgentAdoptMcpDialog); Remove duplicate takes out an entry Coffer's gateway
// already serves; Remove… (⋯) takes any entry out of its file. A config file
// that fails to parse is named above the list, with a way to its Config files
// tab, and its entries stay read-only.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Server, Wrench } from "lucide-react";

import { Section } from "@/components/Section";
import { AgentAdoptMcpDialog } from "@/components/agents/AgentAdoptMcpDialog";
import { AgentMcpEntryDialog } from "@/components/agents/mcp/AgentMcpEntryDialog";
import { AgentOwnMcpRows } from "@/components/agents/mcp/AgentOwnMcpRows";
import { McpParseErrorAlert } from "@/components/agents/mcp/McpParseErrorAlert";
import { useOwnMcpBulk } from "@/components/agents/mcp/useOwnMcpBulk";
import {
  buildOwnMcpRows,
  cofferMcpNames,
  cofferToolGroupNames,
  type OwnMcpRow,
} from "@/components/agents/mcp/mcpRows";
import { AgentKindTab } from "@/components/agents/tabs/AgentKindTab";
import { FromCofferRow } from "@/components/agents/tabs/FromCofferRow";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useAgentConfigFiles, useAgentMcpEntries, useRemoveMcpEntry } from "@/lib/hooks/useAgents";
import { useResources } from "@/lib/hooks/useResources";

export function AgentMcpServersTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const servers = useResources("mcp_server");
  const entries = useAgentMcpEntries(agent.uid);
  const configFiles = useAgentConfigFiles(agent.uid);
  const removeEntry = useRemoveMcpEntry(agent.uid);
  const [adoptTarget, setAdoptTarget] = useState<OwnMcpRow | null>(null);
  const [removeTarget, setRemoveTarget] = useState<OwnMcpRow | null>(null);
  const [viewTarget, setViewTarget] = useState<OwnMcpRow | null>(null);
  const agentLabel = agentTypeLabel(agent.type);

  const parseErrors = useMemo(() => entries.data?.parse_errors ?? [], [entries.data]);
  const rows = useMemo(
    () => buildOwnMcpRows(entries.data?.items ?? [], new Set(parseErrors.map((pe) => pe.source))),
    [entries.data, parseErrors],
  );
  const cofferNames = useMemo(
    () => cofferMcpNames(agent.uid, servers.data ?? []),
    [agent.uid, servers.data],
  );

  const toolGroupNames = useMemo(
    () => cofferToolGroupNames(agent.uid, servers.data ?? []),
    [agent.uid, servers.data],
  );

  // A direct entry's file: its absolute path, home-relative as the row shows it
  // (the key itself until the listing is read).
  const whereLabel = (source: string) => {
    const path =
      configFiles.data?.find((f) => f.key === source)?.path ??
      parseErrors.find((pe) => pe.source === source)?.path;
    return path ? abbreviateHomePath(path) : source;
  };

  const bulk = useOwnMcpBulk({
    agentUid: agent.uid,
    agentName: agent.name,
    agentLabel,
    whereLabel,
  });

  return (
    <div className="flex max-w-[1000px] flex-col gap-8">
      {servers.data ? (
        <FromCofferRow
          icon={Server}
          testId="from-coffer-mcp"
          description={t("agents.mcpTab.fromCoffer.description", { agent: agentLabel })}
          title={t("agents.mcpTab.fromCoffer.title", { count: cofferNames.length })}
          names={cofferNames}
          linkLabel={t("agents.mcpTab.fromCoffer.open")}
          to={`/mcp-servers?agent=${encodeURIComponent(agent.uid)}`}
        />
      ) : null}
      {servers.data ? (
        <FromCofferRow
          icon={Wrench}
          testId="from-coffer-custom-tools"
          description={t("agents.mcpTab.fromCofferTools.description", { agent: agentLabel })}
          title={t("agents.mcpTab.fromCofferTools.title", { count: toolGroupNames.length })}
          names={toolGroupNames}
          linkLabel={t("agents.mcpTab.fromCofferTools.open")}
          to={`/custom-tools?agent=${encodeURIComponent(agent.uid)}`}
        />
      ) : null}

      <Section
        as="h2"
        title={t("agents.mcpTab.own.title", { agent: agentLabel })}
        help={t("agents.mcpTab.own.help")}
        gap="tight"
        testId="own-mcp-section"
      >
        <p className="mb-1 text-xs text-text-muted">
          {t("agents.mcpTab.own.description", { agent: agentLabel })}
        </p>
        <AgentKindTab
          rows={rows}
          searchPlaceholder={t("agents.mcpTab.search")}
          searchText={(row) => row.name}
          isLoading={entries.isPending}
          error={entries.error}
          onRetry={() => void entries.refetch()}
          empty={{
            title: t("agents.mcpTab.emptyTitle", { agent: agentLabel }),
            description: t("agents.mcpTab.emptyDescription", { agent: agentLabel }),
          }}
          noMatch={t("agents.mcpTab.noMatch")}
          bulk={{
            rowKey: (row) => row.key,
            selectable: (row) => row.state !== "readOnly",
            barLabel: t("agents.mcpTab.bulk.label"),
            actions: bulk.actions,
          }}
          notice={
            parseErrors.length > 0 ? (
              <div className="flex flex-col gap-1">
                {parseErrors.map((pe) => (
                  <McpParseErrorAlert
                    key={`${pe.source}:${pe.path}`}
                    agentType={agent.type}
                    error={pe}
                  />
                ))}
              </div>
            ) : undefined
          }
        >
          {(visible, select) => (
            <AgentOwnMcpRows
              rows={visible}
              select={select}
              whereLabel={whereLabel}
              onAdopt={setAdoptTarget}
              onRemoveDuplicate={setRemoveTarget}
              onRemove={setRemoveTarget}
              onOpenEntry={setViewTarget}
            />
          )}
        </AgentKindTab>
      </Section>

      {bulk.dialogs}

      <AgentMcpEntryDialog
        agentUid={agent.uid}
        agentLabel={agentLabel}
        row={viewTarget}
        onClose={() => setViewTarget(null)}
        onAdopt={(row) => {
          setViewTarget(null);
          setAdoptTarget(row);
        }}
        onRemove={(row) => {
          setViewTarget(null);
          setRemoveTarget(row);
        }}
      />

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
    </div>
  );
}
