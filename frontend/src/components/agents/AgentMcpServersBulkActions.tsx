// frontend/src/components/agents/AgentMcpServersBulkActions.tsx
// Bulk action for the agent's direct MCP-servers table: adopt-into-Coffer over
// the selected rows. Adopt uses the same default keychain references the
// single-entry dialog prefills (mcp/{agent}/{entry}/{KEY}) — secret VALUES stay
// in the agent's config; the daemon moves them into the keychain — and fans out
// with allSettled, so entries that need a rename (409 name conflict) just fail
// in the summary rather than aborting the batch. There is no bulk remove:
// Coffer no longer writes another tool's private config. Kept separate to bound
// the tab file.
import { useTranslation } from "react-i18next";

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

  const adoptAll = async () => {
    await adopt.run(rows, (e) =>
      agentsApi.adoptMcpEntry(agentName, e.name, {
        source: e.source,
        secrets: defaultSecretRefs(agentName, e),
      }),
    );
    clear();
  };

  return (
    <Button size="sm" variant="outline" disabled={adopt.isPending} onClick={() => void adoptAll()}>
      {t("agents.workspace.mcp.adopt")}
    </Button>
  );
}
