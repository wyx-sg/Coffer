// frontend/src/pages/AgentDetailPage.tsx — spec agent-registry.
// Per-agent detail page: the shared PageHeader (back link, type chip, the Coffer
// connection / Edit / Delete actions) over eight tabs. The active tab lives in the
// URL (?tab=), so a refresh, a shared link or coming back from a detail page lands
// where the reader was. Leaving Config files with an unsaved draft asks first.
// Only Plugins acts on the agent; Hooks, Memory and Conversations are read-only.
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Pencil, Trash2 } from "lucide-react";

import { AgentConfigFilesEditor } from "@/components/agents/AgentConfigFilesEditor";
import { AgentConversationsTab } from "@/components/agents/AgentConversationsTab";
import { AgentDeleteDialog } from "@/components/agents/AgentDeleteDialog";
import { AgentEditForm } from "@/components/agents/AgentEditForm";
import { AgentConnectionButton } from "@/components/agents/AgentConnectionControls";
import { AgentMcpServersTab } from "@/components/agents/AgentMcpServersTab";
import { AgentMemoryTab } from "@/components/agents/AgentMemoryTab";
import { AgentOverviewTab } from "@/components/agents/AgentOverviewTab";
import { AgentPluginsTab } from "@/components/agents/AgentPluginsTab";
import { AgentHooksTab } from "@/components/agents/AgentHooksTab";
import { AgentHeaderBadges } from "@/components/agents/AgentStateBadges";
import { AgentSkillsTab } from "@/components/agents/AgentSkillsTab";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { useAgent } from "@/lib/hooks/useAgents";
import { displayName } from "@/lib/resourceTitle";
import { ResourceLabel } from "@/components/resource/ResourceLabel";

const TABS = [
  "overview",
  "skills",
  "mcpServers",
  "plugins",
  "hooks",
  "memory",
  "conversations",
  "config",
];
const DEFAULT_TAB = "overview";

export function AgentDetailPage() {
  const { t } = useTranslation();
  const { uid = "" } = useParams<{ uid: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: agent, isPending, error, refetch } = useAgent(uid);
  const [editing, setEditing] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const [pendingTab, setPendingTab] = useState<string | null>(null);

  const requested = searchParams.get("tab");
  const tab = requested && TABS.includes(requested) ? requested : DEFAULT_TAB;
  const setTab = (next: string) => {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next === DEFAULT_TAB) p.delete("tab");
        else p.set("tab", next);
        return p;
      },
      { replace: true },
    );
  };
  const requestTab = (next: string) => {
    if (next === tab) return;
    if (configDirty) setPendingTab(next);
    else setTab(next);
  };

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
      <PageHeader
        back={{ to: "/agents", label: t("agents.detail.back") }}
        title={<ResourceLabel resource={agent} heading />}
        badges={<AgentHeaderBadges agent={agent} />}
        subtitle={agent.description ?? undefined}
        actions={
          <div className="flex items-center gap-2">
            <AgentConnectionButton uid={uid} />
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
        }
      />

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

      <Tabs value={tab} onValueChange={requestTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("agents.workspace.overview")}</TabsTrigger>
          <TabsTrigger value="skills">{t("agents.workspace.skills")}</TabsTrigger>
          <TabsTrigger value="mcpServers">{t("agents.workspace.mcpServers")}</TabsTrigger>
          <TabsTrigger value="plugins">{t("agents.workspace.plugins")}</TabsTrigger>
          <TabsTrigger value="hooks">{t("agents.workspace.hooks")}</TabsTrigger>
          <TabsTrigger value="memory">{t("agents.workspace.memory")}</TabsTrigger>
          <TabsTrigger value="conversations">{t("agents.workspace.conversations")}</TabsTrigger>
          <TabsTrigger value="config">{t("agents.workspace.config")}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-6">
          <AgentOverviewTab agent={agent} />
        </TabsContent>
        <TabsContent value="skills" className="pt-6">
          <AgentSkillsTab agent={agent} />
        </TabsContent>
        <TabsContent value="mcpServers" className="pt-6">
          <AgentMcpServersTab agent={agent} />
        </TabsContent>
        <TabsContent value="plugins" className="pt-6">
          <AgentPluginsTab agent={agent} />
        </TabsContent>
        <TabsContent value="hooks" className="pt-6">
          <AgentHooksTab agent={agent} />
        </TabsContent>
        <TabsContent value="memory" className="pt-6">
          <AgentMemoryTab agent={agent} />
        </TabsContent>
        <TabsContent value="conversations" className="pt-6">
          <AgentConversationsTab uid={uid} />
        </TabsContent>
        <TabsContent value="config" className="pt-6">
          <AgentConfigFilesEditor uid={uid} onDirtyChange={setConfigDirty} />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={pendingTab !== null}
        onOpenChange={(o) => !o && setPendingTab(null)}
        title={t("common.discardChanges.title")}
        description={t("common.discardChanges.body")}
        confirmLabel={t("common.discardChanges.confirm")}
        onConfirm={() => {
          if (pendingTab) setTab(pendingTab);
          setPendingTab(null);
          setConfigDirty(false);
        }}
      />

      <AgentDeleteDialog
        uid={uid}
        name={displayName(agent)}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        onDeleted={() => navigate("/agents")}
      />
    </div>
  );
}
