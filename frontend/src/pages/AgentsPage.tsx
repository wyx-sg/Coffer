// frontend/src/pages/AgentsPage.tsx — spec 004-agent-registry surface.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, Plus } from "lucide-react";

import { AgentAddDialog } from "@/components/agents/AgentAddDialog";
import { AgentTable } from "@/components/agents/AgentTable";
import { BuiltinAgentSection } from "@/components/agents/BuiltinAgentSection";
import { AgentWelcomePanel } from "@/components/agents/AgentWelcomePanel";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useAgents } from "@/lib/hooks/useAgents";
import { useChatAgents } from "@/lib/hooks/useChatAgents";

export function AgentsPage() {
  const { t } = useTranslation();
  const { data: agents, isPending, error, refetch } = useAgents();
  // The built-in chat agent is not a registry agent (no config_dir / config
  // files / MCP install), so it rides the table as a pinned, non-deletable row
  // (see AgentTable). If the chat-agents call fails, the row is simply omitted.
  const { data: chatAgents } = useChatAgents();
  const builtin = (chatAgents ?? []).find((a) => a.agent_key === "builtin") ?? null;
  const [showAdd, setShowAdd] = useState(false);
  const hasAgents = (agents ?? []).length > 0;

  return (
    <div className="space-y-6">
      {/* Header action only once agents exist — the empty state's welcome
          panel carries the add call-to-action instead (no dup). */}
      <PageHeader
        icon={Bot}
        title={t("agents.title")}
        subtitle={t("agents.subtitle")}
        actions={
          hasAgents || builtin ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="mr-1 size-4" /> {t("agents.add")}
            </Button>
          ) : null
        }
      />

      {/* One combined Add dialog — it auto-detects installed agents and also
          offers manual registration behind a disclosure. */}
      <AgentAddDialog open={showAdd} onOpenChange={setShowAdd} onCreated={() => void refetch()} />

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("agents.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : (agents ?? []).length === 0 && !builtin ? (
        <AgentWelcomePanel onAddAgent={() => setShowAdd(true)} />
      ) : (
        // The built-in agent and the managed coding agents have entirely
        // different shapes, so they get separate sections rather than one mixed
        // table.
        <div className="space-y-6">
          {builtin && <BuiltinAgentSection builtin={builtin} />}
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-muted-foreground">
              {t("agents.managedSectionTitle")}
            </h2>
            {(agents ?? []).length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  {t("agents.noManagedAgents")}
                </CardContent>
              </Card>
            ) : (
              <AgentTable agents={agents ?? []} />
            )}
          </section>
        </div>
      )}
    </div>
  );
}
