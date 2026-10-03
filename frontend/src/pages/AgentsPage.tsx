// src/pages/AgentsPage.tsx — spec agent-registry "List the supported agents as fixed rows on the Agents page".
//
// Two fixed rows, Claude Code then Codex, found on their own (on load, when the
// window regains focus, and every few minutes — useAgentTypes), so there is no
// Detect and no Add-agent dialog. On first run, with neither connected and both
// connectable, the header offers Connect both: one preview, one confirmation.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

import {
  AgentConnectionChangeDialog,
  type ConnectionChangeRequest,
} from "@/components/agents/connect/AgentConnectionChangeDialog";
import { AgentsTable, type AgentListRow } from "@/components/agents/list/AgentsTable";
import { useAgentRowState } from "@/components/agents/list/useAgentRowState";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { AGENT_TYPES } from "@/lib/agents/routes";
import { isAddableState } from "@/lib/agents/rowState";
import { translateApiError } from "@/lib/api/errors";
import { useAgentTypes } from "@/lib/hooks/useAgents";

export function AgentsPage() {
  const { t } = useTranslation();
  const types = useAgentTypes();
  const [change, setChange] = useState<ConnectionChangeRequest | null>(null);
  const byType = new Map((types.data ?? []).map((row) => [row.type, row]));
  // Exactly the supported types, in their fixed order.
  const [claudeRow, codexRow] = AGENT_TYPES.map((type) => byType.get(type));
  const claude = useAgentRowState(claudeRow);
  const codex = useAgentRowState(codexRow);
  const rows: AgentListRow[] = [
    { row: claudeRow, state: claude.state },
    { row: codexRow, state: codex.state },
  ].filter((r): r is AgentListRow => !!r.row);

  const firstRun =
    rows.length === AGENT_TYPES.length &&
    rows.every(({ row, state }) => !row.uid && row.addable && !!state && isAddableState(state));

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("agents.title")}
        subtitle={t("agents.list.subtitle")}
        actions={
          firstRun ? (
            <Button onClick={() => setChange({ kind: "add", rows: rows.map((r) => r.row) })}>
              {t("agents.list.connectBoth")}
            </Button>
          ) : null
        }
      />

      {types.error ? (
        <EmptyState
          tone="error"
          title={t("agents.loadFailed")}
          description={translateApiError(t, types.error)}
          action={
            <Button variant="outline" onClick={() => void types.refetch()}>
              <RotateCcw aria-hidden /> {t("common.retry")}
            </Button>
          }
        />
      ) : (
        <AgentsTable rows={rows} isLoading={types.isPending} />
      )}

      <AgentConnectionChangeDialog request={change} onClose={() => setChange(null)} />
    </div>
  );
}
