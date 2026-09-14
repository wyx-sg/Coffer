// frontend/src/components/agents/AgentMcpServersBulkActions.tsx
// Bulk actions for the agent's direct MCP-servers table: adopt-into-Coffer and
// delete-from-the-agent's-config over the selected rows. Adopt uses the same
// default keychain references the single-entry dialog prefills
// (mcp/{agent}/{entry}/{KEY}) — secret VALUES stay in the agent's config; the
// daemon moves them into the keychain — and fans out with allSettled, so
// entries that need a rename (409 name conflict) just fail in the summary
// rather than aborting the batch. Delete is destructive (the daemon writes a
// .bak per touched file) and owns its own confirm dialog. Kept separate to
// bound the tab file.
import { useTranslation } from "react-i18next";

import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { Button } from "@/components/ui/button";
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

  const deleteAll = async () => {
    await remove.run(rows, (e) => agentsApi.removeMcpEntry(agentName, e.name, e.source));
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
      <BulkDeleteButton
        title={t("common.delete")}
        description={t("agents.workspace.mcp.bulkDeleteConfirm", { count: rows.length })}
        pending={remove.isPending}
        onConfirm={deleteAll}
      />
    </>
  );
}
