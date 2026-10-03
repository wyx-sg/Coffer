// src/components/agents/mcp/AgentMcpEntryDialog.tsx — one direct MCP server of an agent, read-only, in a dialog (board 2.1.59, 640).
//
// Spec agent-registry "Show one direct MCP entry's full configuration without
// its secrets". Reached from the name on the agent's MCP servers tab. A direct
// entry has one thing to show — its JSON as the agent's own config file holds
// it — so it opens as a dialog over the list rather than a page of its own
// (.agents/frontend.md "A page only when there is a page's worth"). The two
// writes the row carries sit in the footer around Close (ghost): take it out of
// the file (Remove, or Remove duplicate when Coffer already has it) on the
// left, adopt it into Coffer on the right.
// The entry has no uid: it is addressed by its name and the config file's key.
import { useTranslation } from "react-i18next";

import { AgentMcpEntryOverview } from "@/components/agents/AgentMcpEntryOverview";
import type { OwnMcpRow } from "@/components/agents/mcp/mcpRows";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAgentMcpEntry } from "@/lib/hooks/useAgents";

interface Props {
  agentUid: string;
  /** The agent's product name, for "{agent}'s own server". */
  agentLabel: string;
  /** The row opened; null keeps the dialog closed. */
  row: OwnMcpRow | null;
  onClose: () => void;
  onAdopt: (row: OwnMcpRow) => void;
  onRemove: (row: OwnMcpRow) => void;
}

export function AgentMcpEntryDialog({
  agentUid,
  agentLabel,
  row,
  onClose,
  onAdopt,
  onRemove,
}: Props) {
  const { t } = useTranslation();
  const entry = useAgentMcpEntry(agentUid, row?.name ?? "", row?.entry.source ?? "");
  const readOnly = row?.state === "readOnly";
  const duplicate = row?.entry.matches_resource ?? null;

  return (
    <Dialog open={row !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-[640px]">
        <DialogHeader>
          <DialogTitle className="font-mono">{row?.name}</DialogTitle>
          <DialogDescription>
            {t("agents.mcpTab.entry.description", { agent: agentLabel })}
          </DialogDescription>
        </DialogHeader>

        {entry.isPending ? (
          <Skeleton className="h-40 w-full" aria-busy="true" />
        ) : entry.error || !entry.data ? (
          <p className="text-sm text-danger" role="alert">
            {entry.error
              ? translateApiError(t, entry.error)
              : t("agents.workspace.mcp.detail.loadFailed")}
          </p>
        ) : (
          <AgentMcpEntryOverview entry={entry.data} />
        )}

        <DialogFooter className="sm:justify-between">
          <Button variant="danger" disabled={readOnly || !row} onClick={() => row && onRemove(row)}>
            {duplicate !== null ? t("agents.mcpTab.removeDuplicate") : t("agents.mcpTab.remove")}
          </Button>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={onClose}>
              {t("common.close")}
            </Button>
            {duplicate === null ? (
              <Button disabled={readOnly || !row} onClick={() => row && onAdopt(row)}>
                {t("agents.mcpTab.adopt")}
              </Button>
            ) : null}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
