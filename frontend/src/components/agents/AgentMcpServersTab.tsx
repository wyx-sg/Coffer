// frontend/src/components/agents/AgentMcpServersTab.tsx
// "MCP servers" tab on the agent detail page, in two sections:
//
//   A. Via Coffer gateway — Coffer's shim install status plus a link to the
//      standalone MCP servers page (the exposed servers are managed there, not
//      re-listed here). Extracted to AgentGatewayMcpSection.tsx to keep this
//      file inside the size cap.
//
//   B. Direct servers — the agent's own MCP entries read from its config
//      files (specs agent-registry/005 workspace amendment). Name, description, and two
//      actions: adopt the entry into Coffer, or delete it from the agent's own
//      config file (behind a confirm — the daemon writes a .bak).
//
//      The description IS the transport: an MCP config entry carries no
//      description field in either format, and the command line (or URL) is the
//      only text on it that says what the server actually is. `source` and
//      `enabled` stay on the wire type — the CLI prints them, and adopt/delete
//      still carry `source` — but neither earns a column: `enabled` is not
//      editable here, and `source` only ever disambiguates the one case where
//      it can, `claude_code` carrying the SAME entry name in both of its config
//      files. So it renders as a badge beside the name for duplicated names
//      only. Entries that duplicate an existing Coffer resource get an inline
//      hint. Config files that failed to parse are surfaced in a banner; their
//      entries can't be listed, so the banner is the only signal.
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import type { McpEntryOut } from "@/lib/api/agents";
import { useAgentMcpEntries, useRemoveMcpEntry } from "@/lib/hooks/useAgents";

export function AgentMcpServersTab({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const entries = useAgentMcpEntries(agentName);
  const removeEntry = useRemoveMcpEntry(agentName);
  const [adoptTarget, setAdoptTarget] = useState<McpEntryOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<McpEntryOut | null>(null);

  // The `coffer` entry IS the gateway hookup — it's section A's concern, so
  // the direct list only shows the agent's other (non-Coffer) servers.
  const directEntries = (entries.data?.items ?? []).filter((e) => !e.is_coffer);
  const parseErrors = entries.data?.parse_errors ?? [];
  // Entry names are unique per file, not across files: only `claude_code` can
  // list the same name twice (~/.claude.json and settings.json). Badge the
  // source on exactly those rows, so the user can tell which is which before
  // adopting or deleting one — and nowhere else.
  const duplicated = new Set(
    directEntries.map((e) => e.name).filter((n, i, all) => all.indexOf(n) !== i),
  );

  const directColumns: Column<McpEntryOut>[] = [
    {
      key: "name",
      header: t("resources.cols.name"),
      className: "whitespace-nowrap",
      cell: (e) => (
        <div className="space-y-1">
          <span className="flex items-center gap-2">
            <span className="font-medium">{e.name}</span>
            {duplicated.has(e.name) && <Badge variant="secondary">{e.source}</Badge>}
          </span>
          {e.matches_resource !== null && (
            <p className="text-xs text-muted-foreground">
              {t("agents.workspace.mcp.alreadyInCoffer", { name: e.matches_resource })}
            </p>
          )}
        </div>
      ),
    },
    {
      key: "description",
      header: t("resources.cols.description"),
      cell: (e) => (
        <span className="flex items-center gap-2">
          <Badge variant="outline">{e.transport}</Badge>
          <span className="line-clamp-1 max-w-md font-mono text-xs text-muted-foreground">
            {e.transport === "stdio"
              ? [e.command, ...e.args].filter(Boolean).join(" ")
              : (e.url ?? "")}
          </span>
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (e) => (
        <span className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={() => setAdoptTarget(e)}>
            {t("agents.workspace.mcp.adopt")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            onClick={() => setDeleteTarget(e)}
          >
            {t("common.delete")}
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

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("common.delete")}: {deleteTarget?.name}
            </DialogTitle>
            <DialogDescription>{t("agents.workspace.mcp.deleteConfirm")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={removeEntry.isPending}
              onClick={() => {
                if (!deleteTarget) return;
                removeEntry.mutate(
                  { entry: deleteTarget.name, source: deleteTarget.source },
                  { onSuccess: () => setDeleteTarget(null) },
                );
              }}
            >
              {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
