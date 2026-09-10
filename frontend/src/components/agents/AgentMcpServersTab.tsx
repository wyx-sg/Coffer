// frontend/src/components/agents/AgentMcpServersTab.tsx
// "MCP servers" tab on the agent detail page, in two sections:
//
//   A. Via Coffer gateway — Coffer's shim install status plus a link to the
//      standalone MCP servers page (the exposed servers are managed there, not
//      re-listed here). Extracted to AgentGatewayMcpSection.tsx to keep this
//      file inside the size cap.
//
//   B. Direct servers — the agent's own MCP entries read from its config
//      files (specs 004/005 workspace amendment). The listing is read-only and
//      the one write is adopt-into-Coffer: each row shows source/transport, the
//      entry's enabled state as a plain badge (null for claude_code, whose
//      config format has no per-entry flag), and an Adopt action. Coffer no
//      longer edits another tool's private config, so there is no delete and no
//      toggle; entries that duplicate an existing Coffer resource just get an
//      inline hint. Config files that failed to parse are surfaced in a banner;
//      their entries can't be listed, so the banner is the only signal.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentAdoptMcpDialog } from "@/components/agents/AgentAdoptMcpDialog";
import { AgentGatewayMcpSection } from "@/components/agents/AgentGatewayMcpSection";
import { AgentMcpServersBulkActions } from "@/components/agents/AgentMcpServersBulkActions";
import { DataTable, type Column } from "@/components/DataTable";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import type { McpEntryOut } from "@/lib/api/agents";
import { useAgentMcpEntries } from "@/lib/hooks/useAgents";

export function AgentMcpServersTab({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const entries = useAgentMcpEntries(agentName);
  const [adoptTarget, setAdoptTarget] = useState<McpEntryOut | null>(null);

  // The `coffer` entry IS the gateway hookup — it's section A's concern, so
  // the direct list only shows the agent's other (non-Coffer) servers.
  const directEntries = (entries.data?.items ?? []).filter((e) => !e.is_coffer);
  const parseErrors = entries.data?.parse_errors ?? [];

  const directColumns: Column<McpEntryOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (e) => (
        <div className="space-y-1">
          <span className="font-medium">{e.name}</span>
          {e.matches_resource !== null && (
            <p className="text-xs text-muted-foreground">
              {t("agents.workspace.mcp.alreadyInCoffer", { name: e.matches_resource })}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "source",
      header: t("agents.workspace.mcp.source"),
      className: "whitespace-nowrap",
      cell: (e) => <Badge variant="secondary">{e.source}</Badge>,
    },
    {
      key: "transport",
      header: t("agents.workspace.mcp.transport"),
      cell: (e) => (
        <span className="flex items-center gap-2">
          <Badge variant="outline">{e.transport}</Badge>
          <span className="line-clamp-1 max-w-xs font-mono text-xs text-muted-foreground">
            {e.transport === "stdio"
              ? [e.command, ...e.args].filter(Boolean).join(" ")
              : (e.url ?? "")}
          </span>
        </span>
      ),
    },
    {
      key: "enabled",
      header: t("agents.workspace.mcp.enabled"),
      className: "whitespace-nowrap",
      // Read-only: `enabled` is null when the agent's config format has no
      // per-entry enable flag (claude_code). Flipping it would mean writing the
      // agent's own config, which Coffer no longer does.
      cell: (e) =>
        e.enabled === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <Badge variant={e.enabled ? "secondary" : "outline"}>
            {e.enabled ? t("common.enabled") : t("common.disabled")}
          </Badge>
        ),
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (e) => (
        <span className="flex justify-end">
          <Button size="sm" variant="outline" onClick={() => setAdoptTarget(e)}>
            {t("agents.workspace.mcp.adopt")}
          </Button>
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* A. Via Coffer gateway — renders its own card (install status or the
          shared "open the MCP servers page" link). */}
      <AgentGatewayMcpSection agentName={agentName} />

      {/* B. Direct servers (the agent's own config entries) */}
      <Card className="space-y-3 p-4">
        <h3 className="text-sm font-medium text-muted-foreground">
          {t("agents.workspace.mcp.directTitle")}
        </h3>

        {parseErrors.length > 0 && (
          <Alert variant="destructive">
            <AlertDescription>
              <p className="font-medium">{t("agents.workspace.mcp.parseError")}</p>
              <ul className="mt-1 space-y-0.5">
                {parseErrors.map((pe) => (
                  <li key={`${pe.source}:${pe.path}`} className="font-mono text-xs">
                    {pe.source}: {pe.error}
                  </li>
                ))}
              </ul>
            </AlertDescription>
          </Alert>
        )}

        {entries.isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : entries.error ? (
          <p className="text-sm text-destructive">{translateApiError(t, entries.error)}</p>
        ) : (
          <DataTable
            rows={directEntries}
            columns={directColumns}
            rowKey={(e) => `${e.source}:${e.name}`}
            search={{
              accessor: (e) => e.name,
              placeholder: t("agents.workspace.mcp.searchPlaceholder"),
            }}
            selection={{
              ariaSelectAll: t("common.bulk.selectAll"),
              ariaSelectRow: (e) => `${t("common.bulk.selectRow")}: ${e.name}`,
              bulkLabel: (count) => t("common.bulk.selected", { count }),
              clearLabel: t("common.clear"),
              renderBulkActions: ({ selectedRows, clear }) => (
                <AgentMcpServersBulkActions
                  agentName={agentName}
                  rows={selectedRows}
                  clear={clear}
                />
              ),
            }}
            emptyMessage={t("agents.workspace.mcp.empty")}
          />
        )}
      </Card>

      {adoptTarget && (
        <AgentAdoptMcpDialog
          agentName={agentName}
          entry={adoptTarget}
          open
          onOpenChange={(open) => {
            if (!open) setAdoptTarget(null);
          }}
        />
      )}
    </div>
  );
}
