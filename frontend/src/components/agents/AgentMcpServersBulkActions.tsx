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
import { agentMcpEntriesKey, resourcesByKindKey } from "@/lib/api/queryKeys";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";

/** Where an adopted entry's secrets are stored. The ref spells the agent's
 *  NAME because a credential ref is an address a person reads in the vault,
 *  and it is minted once at adoption — nothing ever looks one up by name, so a
 *  later rename leaves the stored refs intact and still resolving. */
function defaultSecretRefs(agentName: string, entry: McpEntryOut): Record<string, string> {
  return Object.fromEntries(
    entry.secret_keys.map((key) => [key, `mcp/${agentName}/${entry.name}/${key}`]),
  );
}

export function AgentMcpServersBulkActions({
  agentUid,
  agentName,
  rows,
  clear,
}: {
  /** The agent being adopted from — what every request is addressed to. */
  agentUid: string;
  /** Its label, which the minted credential refs spell. */
  agentName: string;
  rows: McpEntryOut[];
  clear: () => void;
}) {
  const { t } = useTranslation();
  const adopt = useBulkMutate({
    invalidate: [agentMcpEntriesKey(agentUid), resourcesByKindKey("mcp_server")],
  });
  const remove = useBulkMutate({ invalidate: [agentMcpEntriesKey(agentUid)] });

  const adoptAll = async () => {
    await adopt.run(rows, (e) =>
      agentsApi.adoptMcpEntry(agentUid, e.name, {
        source: e.source,
        secrets: defaultSecretRefs(agentName, e),
      }),
    );
    clear();
  };

  const deleteAll = async () => {
    await remove.run(rows, (e) => agentsApi.removeMcpEntry(agentUid, e.name, e.source));
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
