// frontend/src/pages/AgentMcpEntryPage.tsx — spec agent-registry "Show one
// direct MCP entry's full configuration without its secrets".
// One direct (unmanaged) MCP server of an agent, reached by clicking its name
// in the Direct servers table: what the agent's own config file holds for it,
// read-only, with the two writes the table row offers — adopt it into Coffer,
// or delete it from the file.
//
// The entry has no uid — it is a stanza in someone else's file, which Coffer
// did not mint — so it is addressed the way the REST route addresses it: the
// entry's name in the path, and `?source=` naming the file, because
// claude_code can carry the same name in two of them.
import { useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { AgentAdoptMcpDialog } from "@/components/agents/AgentAdoptMcpDialog";
import { AgentMcpEntryOverview } from "@/components/agents/AgentMcpEntryOverview";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import { useAgent, useAgentMcpEntry, useRemoveMcpEntry } from "@/lib/hooks/useAgents";

export function AgentMcpEntryPage() {
  const { t } = useTranslation();
  const { uid = "", entry: entryName = "" } = useParams<{ uid: string; entry: string }>();
  const source = useSearchParams()[0].get("source") ?? "";
  const navigate = useNavigate();
  const agent = useAgent(uid);
  const { data: entry, isPending, error } = useAgentMcpEntry(uid, entryName, source);
  const removeEntry = useRemoveMcpEntry(uid);
  const [adoptOpen, setAdoptOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // The agent page keeps its tab in `?tab=`, so the way back lands on the MCP
  // servers tab the row was on. The table passes the target (and the agent's
  // name as its label) in location.state, as the managed detail pages take
  // it; a reload or a pasted link has no state, so the same target is rebuilt.
  const backState = useLocation().state as { backTo?: string; backLabel?: string } | null;
  const agentName = agent.data?.name ?? "";
  const back = {
    to: backState?.backTo ?? `/agents/${encodeURIComponent(uid)}?tab=mcpServers`,
    label: t("common.backTo", {
      label: backState?.backLabel ?? (agentName || t("agents.workspace.mcpServers")),
    }),
  };

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={entryName} />
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      </div>
    );
  }
  if (error || !entry) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={entryName} />
        <Card className="border-destructive/40">
          <CardContent className="py-6">
            <p className="text-sm text-destructive" role="alert">
              {error ? translateApiError(t, error) : t("agents.workspace.mcp.detail.loadFailed")}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={entry.name}
        badges={
          <>
            <Badge variant="secondary">
              {t("agents.workspace.mcp.directBadge", { agent: agentName || "…" })}
            </Badge>
            <Badge variant="outline">{entry.transport}</Badge>
          </>
        }
        subtitle={
          <>
            <span className="block">{t("agents.workspace.mcp.detail.hint")}</span>
            {entry.matches_resource !== null ? (
              <span className="block">
                {t("agents.workspace.mcp.alreadyInCoffer", { name: entry.matches_resource })}
              </span>
            ) : null}
          </>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setAdoptOpen(true)}>
              {t("agents.workspace.mcp.adopt")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDeleteOpen(true)}
              className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
            </Button>
          </div>
        }
      />

      <AgentMcpEntryOverview entry={entry} />

      {/* Mounted only once the agent's name is known: the dialog mints the
          credential refs it prefills from that name. */}
      {adoptOpen && agent.data ? (
        <AgentAdoptMcpDialog
          agentUid={uid}
          agentName={agent.data.name}
          entry={entry}
          open
          onOpenChange={setAdoptOpen}
          onAdopted={(created) =>
            navigate(created.name ? `/mcp-servers/${encodeURIComponent(created.name)}` : back.to)
          }
        />
      ) : null}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("agents.removeConfirmTitle", { name: entry.name })}
        description={t("agents.workspace.mcp.deleteConfirm")}
        confirmLabel={removeEntry.isPending ? t("common.deleting") : t("common.delete")}
        pending={removeEntry.isPending}
        onConfirm={() =>
          removeEntry.mutate(
            { entry: entry.name, source: entry.source },
            { onSuccess: () => navigate(back.to) },
          )
        }
      />
    </div>
  );
}
