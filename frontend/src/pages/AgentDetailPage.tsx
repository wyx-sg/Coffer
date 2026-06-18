// frontend/src/pages/AgentDetailPage.tsx — spec 004-agent-registry.
// Per-agent detail page: a back link, a header with the Coffer-MCP install
// button + edit + delete, and two tabs — Overview and Config files. Editing
// opens a modal dialog (AgentEditForm). Agents have no enable/disable concept.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";

import { AgentConfigFilesEditor } from "@/components/agents/AgentConfigFilesEditor";
import { AgentConversationsTab } from "@/components/agents/AgentConversationsTab";
import { AgentEditForm } from "@/components/agents/AgentEditForm";
import { AgentInstructionsTab } from "@/components/agents/AgentInstructionsTab";
import { AgentMcpButton } from "@/components/agents/AgentMcpControls";
import { AgentMcpServersTab } from "@/components/agents/AgentMcpServersTab";
import { AgentMemoryTab } from "@/components/agents/AgentMemoryTab";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentPluginsTab } from "@/components/agents/AgentPluginsTab";
import { AgentSkillsTab } from "@/components/agents/AgentSkillsTab";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { useAgent, useRemoveAgent } from "@/lib/hooks/useAgents";

export function AgentDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: agent, isPending, error, refetch } = useAgent(name);
  const remove = useRemoveAgent();
  const [editing, setEditing] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error || !agent) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">{t("agents.loadFailed")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {error ? translateApiError(t, error) : t("agents.loadFailed")}
          </p>
          <Button variant="link" onClick={() => navigate("/agents")} className="-ml-2">
            <ArrowLeft className="mr-1 size-4" />
            {t("agents.detail.back")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/agents")}
        className="-ml-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" /> {t("agents.detail.back")}
      </Button>

      <div className="space-y-2">
        {/* Title + actions on one row; the description sits below the title. */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="font-serif text-3xl tracking-tight">{agent.name}</h1>
            <Badge variant="secondary">{agent.type}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <AgentMcpButton name={name} />
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil className="mr-1.5 size-3.5" /> {t("agents.edit")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setDeleteOpen(true)}
            >
              <Trash2 className="mr-1.5 size-3.5" /> {t("common.delete")}
            </Button>
          </div>
        </div>
        {agent.description ? (
          <p className="max-w-prose text-sm text-muted-foreground">{agent.description}</p>
        ) : null}
      </div>

      {editing ? (
        <AgentEditForm
          agent={agent}
          onClose={() => setEditing(false)}
          onSaved={() => {
            void refetch();
            setEditing(false);
          }}
        />
      ) : null}

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t("agents.workspace.overview")}</TabsTrigger>
          <TabsTrigger value="skills">{t("agents.workspace.skills")}</TabsTrigger>
          <TabsTrigger value="mcpServers">{t("agents.workspace.mcpServers")}</TabsTrigger>
          <TabsTrigger value="plugins">{t("agents.workspace.plugins")}</TabsTrigger>
          <TabsTrigger value="memory">{t("agents.workspace.memory")}</TabsTrigger>
          <TabsTrigger value="conversations">{t("agents.workspace.conversations")}</TabsTrigger>
          <TabsTrigger value="config">{t("agents.workspace.config")}</TabsTrigger>
          <TabsTrigger value="instructions">{t("agents.workspace.instructions")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <AgentOverviewTab agent={agent} />
        </TabsContent>

        <TabsContent value="skills" className="pt-6">
          <AgentSkillsTab agent={agent} />
        </TabsContent>

        <TabsContent value="mcpServers" className="pt-6">
          <AgentMcpServersTab agentName={name} />
        </TabsContent>

        <TabsContent value="plugins" className="pt-6">
          <AgentPluginsTab agent={agent} />
        </TabsContent>

        <TabsContent value="memory" className="pt-6">
          <AgentMemoryTab agent={agent} />
        </TabsContent>

        <TabsContent value="conversations" className="pt-6">
          <AgentConversationsTab name={name} />
        </TabsContent>

        <TabsContent value="config" className="pt-6">
          <AgentConfigFilesEditor name={name} />
        </TabsContent>

        <TabsContent value="instructions" className="pt-6">
          <AgentInstructionsTab name={name} />
        </TabsContent>
      </Tabs>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("agents.removeConfirm", { name })}</DialogTitle>
            <DialogDescription>{t("agents.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(name, {
                  onSuccess: () => {
                    setDeleteOpen(false);
                    navigate("/agents");
                  },
                })
              }
            >
              {remove.isPending ? t("common.deleting") : t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
