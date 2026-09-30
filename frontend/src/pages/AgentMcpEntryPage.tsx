// src/pages/AgentMcpEntryPage.tsx — one direct MCP server of an agent, read-only, at /agents/:type/mcp-servers/:entry.
//
// Spec agent-registry "Show one direct MCP entry's full configuration without
// its secrets". Reached from the name on the agent's MCP servers tab: what the
// agent's own config file holds for the entry, with the row's two writes —
// adopt it into Coffer (then on to the new managed server), or remove it from
// the file (then back to the tab). The entry has no uid: it is addressed by its
// name and `?source=` (the config file's key, since claude_code can carry the
// same name in two files); the agent by its type (`useAgentRoute`).
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Import, Trash2 } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { AgentAdoptMcpDialog } from "@/components/agents/AgentAdoptMcpDialog";
import { AgentMcpEntryOverview } from "@/components/agents/AgentMcpEntryOverview";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import { translateApiError } from "@/lib/api/errors";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";
import { useAgentMcpEntry, useRemoveMcpEntry } from "@/lib/hooks/useAgents";

export function AgentMcpEntryPage() {
  const { t } = useTranslation();
  const { entry: entryName = "" } = useParams<{ entry: string }>();
  const source = useSearchParams()[0].get("source") ?? "";
  const navigate = useNavigate();
  const route = useAgentRoute();
  const { data: entry, isPending, error } = useAgentMcpEntry(route.uid, entryName, source);
  const removeEntry = useRemoveMcpEntry(route.uid);
  const [adoptOpen, setAdoptOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);

  const type = route.type ?? "";
  const agentLabel = agentTypeLabel(type);
  // No way back from an address whose segment is not a type.
  const back = type
    ? {
        to: agentTabPath(type, "mcp-servers"),
        label: t("common.backTo", { label: t("agents.workspace.mcpServers") }),
      }
    : undefined;

  if (route.isPending || (route.uid && isPending)) {
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
  if (error || route.error || !entry) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={entryName} />
        <Card className="border-destructive/40">
          <CardContent className="py-6">
            <p className="text-sm text-destructive" role="alert">
              {error || route.error
                ? translateApiError(t, error ?? route.error)
                : t("agents.workspace.mcp.detail.loadFailed")}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const fileLabel = abbreviateHomePath(entry.path);
  const duplicate = entry.matches_resource;

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={entry.name}
        badges={
          <>
            <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
              <AgentBadge type={type} size="sm" tooltip={false} />
              {t("agents.mcpTab.directOf", { agent: agentLabel })}
            </span>
            <Badge variant="outline">{entry.transport}</Badge>
          </>
        }
        subtitle={
          <>
            <span className="block">{t("agents.workspace.mcp.detail.hint")}</span>
            {duplicate !== null ? (
              <span className="block">{t("agents.mcpTab.duplicateOf", { name: duplicate })}</span>
            ) : null}
          </>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => setAdoptOpen(true)}>
              <Import aria-hidden /> {t("agents.mcpTab.adopt")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setRemoveOpen(true)}
              className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 aria-hidden /> {t("agents.mcpTab.remove")}
            </Button>
          </div>
        }
      />

      <AgentMcpEntryOverview entry={entry} />

      {adoptOpen && route.agent ? (
        <AgentAdoptMcpDialog
          agentUid={route.uid}
          agentName={route.agent.name}
          agentLabel={agentLabel}
          fileLabel={fileLabel}
          entry={entry}
          open
          onOpenChange={setAdoptOpen}
          onAdopted={(created) => navigate(`/mcp-servers/${encodeURIComponent(created.name)}`)}
        />
      ) : null}

      <ConfirmDialog
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        title={t("agents.mcpTab.removeTitle", { name: entry.name, file: fileLabel })}
        description={
          duplicate !== null
            ? t("agents.mcpTab.removeDuplicateBody", { agent: agentLabel, name: duplicate })
            : t("agents.mcpTab.removeBody", { agent: agentLabel })
        }
        confirmLabel={t("agents.mcpTab.remove")}
        pending={removeEntry.isPending}
        onConfirm={() =>
          removeEntry.mutate(
            { entry: entry.name, source: entry.source },
            { onSuccess: () => navigate(agentTabPath(type, "mcp-servers")) },
          )
        }
      />
    </div>
  );
}
