// frontend/src/components/agents/AgentMcpServersTab.tsx
// "MCP servers" tab on the agent detail page, in two sections:
//
//   A. Via Coffer gateway — Coffer's shim install status plus a link to the
//      standalone MCP servers page (the exposed servers are managed there, not
//      re-listed here). Extracted to AgentGatewayMcpSection.tsx to keep this
//      file inside the size cap.
//
//   B. Direct servers — the agent's own MCP entries read from its config
//      files (specs 004/005 workspace amendment). Each row shows source/transport, a per-entry enable
//      Switch when the agent supports it (codex; `enabled` is null for
//      claude_code), and actions to adopt the entry into Coffer or remove it
//      (with a confirm — removal writes a .bak). Entries that duplicate an
//      existing Coffer resource get an inline hint + a remove-duplicate
//      shortcut. Config files that failed to parse are surfaced in a banner;
//      their entries can't be listed, so the banner is the only signal.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentAdoptMcpDialog } from "@/components/agents/AgentAdoptMcpDialog";
import { AgentGatewayMcpSection } from "@/components/agents/AgentGatewayMcpSection";
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
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import type { McpEntryOut } from "@/lib/api/agents";
import { useAgentMcpEntries, useRemoveMcpEntry, useToggleMcpEntry } from "@/lib/hooks/useAgents";

export function AgentMcpServersTab({ agentName }: { agentName: string }) {
  const { t } = useTranslation();
  const entries = useAgentMcpEntries(agentName);
  const toggle = useToggleMcpEntry(agentName);
  const removeEntry = useRemoveMcpEntry(agentName);
  const [adoptTarget, setAdoptTarget] = useState<McpEntryOut | null>(null);
  const [removeTarget, setRemoveTarget] = useState<McpEntryOut | null>(null);

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
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{t("agents.workspace.mcp.alreadyInCoffer", { name: e.matches_resource })}</span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={() => setRemoveTarget(e)}
              >
                {t("agents.workspace.mcp.removeDuplicate")}
              </Button>
            </div>
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
      // `enabled` is null when the agent's config format has no per-entry
      // enable flag (claude_code) — no Switch in that case.
      cell: (e) =>
        e.enabled === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <Switch
            checked={e.enabled}
            disabled={toggle.isPending}
            onCheckedChange={(checked) => toggle.mutate({ entry: e.name, enabled: checked })}
            aria-label={`${t("agents.workspace.mcp.enabled")}: ${e.name}`}
          />
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
            onClick={() => setRemoveTarget(e)}
          >
            {t("agents.workspace.mcp.remove")}
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
        open={removeTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRemoveTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("agents.workspace.mcp.remove")}: {removeTarget?.name}
            </DialogTitle>
            <DialogDescription>{t("agents.workspace.mcp.removeConfirm")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRemoveTarget(null)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={removeEntry.isPending}
              onClick={() => {
                if (!removeTarget) return;
                removeEntry.mutate(
                  { entry: removeTarget.name, source: removeTarget.source },
                  { onSuccess: () => setRemoveTarget(null) },
                );
              }}
            >
              {t("agents.workspace.mcp.remove")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
