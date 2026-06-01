// frontend/src/pages/AgentsPage.tsx — spec 004-agent-registry surface.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Bot, Plus } from "lucide-react";

import { AgentAddDialog } from "@/components/agents/AgentAddDialog";
import { AgentTable } from "@/components/agents/AgentTable";
import { AgentWelcomePanel } from "@/components/agents/AgentWelcomePanel";
import { BuiltinAgentsSection } from "@/components/agents/BuiltinAgentsSection";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useAgents } from "@/lib/hooks/useAgents";

export function AgentsPage() {
  const { t } = useTranslation();
  const { data: agents, isPending, error, refetch } = useAgents();
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
          hasAgents ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="mr-1 size-4" /> {t("agents.add")}
            </Button>
          ) : null
        }
      />

      {/* Coffer's own built-in LLM agent(s) — surfaced here so they can be
          viewed / created / edited / deleted, not just picked in Chat. */}
      <BuiltinAgentsSection />

      {/* One combined Add dialog — it auto-detects installed agents and also
          offers manual registration behind a disclosure. */}
      <AgentAddDialog open={showAdd} onOpenChange={setShowAdd} onCreated={() => void refetch()} />

      {/* Header for the managed external agents that follow below. */}
      <h2 className="text-lg font-semibold">{t("agents.managedHeading")}</h2>

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
      ) : (agents ?? []).length === 0 ? (
        <AgentWelcomePanel onAddAgent={() => setShowAdd(true)} />
      ) : (
        <AgentTable agents={agents ?? []} />
      )}
    </div>
  );
}
