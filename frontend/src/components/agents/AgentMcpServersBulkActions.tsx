// frontend/src/components/agents/AgentMcpServersBulkActions.tsx
// Bulk actions for the agent's direct MCP-servers table: adopt-into-Coffer and
// remove over the selected rows. Adopt uses the same default keychain references
// the single-entry dialog prefills (mcp/{agent}/{entry}/{KEY}) — secret VALUES
// stay in the agent's config; the daemon moves them into the keychain — and fans
// out with allSettled, so entries that need a rename (409 name conflict) just
// fail in the summary rather than aborting the batch. Remove is destructive and
// owns its own confirm dialog. Kept separate to bound the tab file.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { agentsApi, type McpEntryOut } from "@/lib/api/agents";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

function defaultSecretRefs(agentName: string, entry: McpEntryOut): Record<string, string> {
  return Object.fromEntries(
    entry.secret_keys.map((key) => [key, `mcp/${agentName}/${entry.name}/${key}`]),
  );
}

export function AgentMcpServersBulkActions({
  agentName,
  rows,
  clear,
}: {
  agentName: string;
  rows: McpEntryOut[];
  clear: () => void;
}) {
  const { t } = useTranslation();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const adopt = useBulkMutate({
    invalidate: [
      ["agents", agentName, "mcp-entries"],
      ["resources", { kind: "mcp_server" }],
    ],
  });
  const remove = useBulkMutate({ invalidate: [["agents", agentName, "mcp-entries"]] });

  const adoptAll = async () => {
    await adopt.run(rows, (e) =>
      agentsApi.adoptMcpEntry(agentName, e.name, {
        source: e.source,
        secrets: defaultSecretRefs(agentName, e),
      }),
    );
    clear();
  };

  const removeAll = async () => {
    await remove.run(rows, (e) => agentsApi.removeMcpEntry(agentName, e.name, e.source));
    setConfirmRemove(false);
    clear();
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        disabled={adopt.isPending}
        onClick={() => void adoptAll()}
      >
        {t("agents.workspace.mcp.adopt")}
      </Button>
      <Button
        size="sm"
        variant="outline"
        className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
        disabled={remove.isPending}
        onClick={() => setConfirmRemove(true)}
      >
        {t("agents.workspace.mcp.remove")}
      </Button>

      <Dialog open={confirmRemove} onOpenChange={setConfirmRemove}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("agents.workspace.mcp.remove")}</DialogTitle>
            <DialogDescription>
              {t("agents.workspace.mcp.bulkRemoveConfirm", { count: rows.length })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmRemove(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => void removeAll()}
            >
              {t("agents.workspace.mcp.remove")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
