// frontend/src/pages/BuiltinAgentDetailPage.tsx — spec 008.
// Detail page for a built-in agent (kind `builtin_agent`), mirroring the
// external agent detail page. A back link, a header (name + edit/delete; delete
// surfaces the 409 CANNOT_DELETE_LAST_BUILTIN_AGENT inline), and four tabs:
//   • Overview — model (read-only) + whether its provider key is configured,
//     gateway on/off, confirm_tools, created/updated.
//   • Config   — edit BEHAVIOUR only (system_prompt, temperature, max_tokens,
//     use_gateway, confirm_tools); model + credential_ref are read-only here
//     (they're set in Settings → AI).
//   • Skill    — READ-ONLY skills available via Coffer's gateway.
//   • MCP      — READ-ONLY MCP servers the gateway aggregates.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, Pencil, Trash2 } from "lucide-react";

import { BuiltinAgentForm } from "@/components/agents/BuiltinAgentForm";
import { BuiltinAgentMcpServersTab } from "@/components/agents/BuiltinAgentMcpServersTab";
import { BuiltinAgentSkillsTab } from "@/components/agents/BuiltinAgentSkillsTab";
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
import { providerFromModel } from "@/lib/aiProviders";
import { useBuiltinAgent, useRemoveBuiltinAgent } from "@/lib/hooks/useBuiltinAgents";
import { formatDateTime } from "@/lib/utils";

export function BuiltinAgentDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const { data: agent, isPending, error, refetch } = useBuiltinAgent(name);
  const remove = useRemoveBuiltinAgent();
  const [editing, setEditing] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  // Built-in delete may 409 (CANNOT_DELETE_LAST_BUILTIN_AGENT) — shown inline.
  const [deleteError, setDeleteError] = useState<string | null>(null);

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
          <CardTitle className="text-destructive">{t("builtinAgents.loadFailed")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {error ? translateApiError(t, error) : t("builtinAgents.loadFailed")}
          </p>
          <Button variant="link" onClick={() => navigate("/agents")} className="-ml-2">
            <ArrowLeft className="mr-1 size-4" />
            {t("builtinAgents.detail.back")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  const config = agent.config;
  const useGateway = config.use_gateway ?? true;
  const provider = providerFromModel(config.model);
  const keyConfigured = !!config.credential_ref;

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate("/agents")}
        className="-ml-2 text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1.5 size-4" /> {t("builtinAgents.detail.back")}
      </Button>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="font-serif text-3xl tracking-tight">{agent.name}</h1>
            <Badge variant="secondary">{t("agents.typeBuiltin")}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              <Pencil className="mr-1.5 size-3.5" /> {t("agents.edit")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:border-destructive/40 hover:bg-destructive/10 hover:text-destructive"
              onClick={() => {
                setDeleteError(null);
                setDeleteOpen(true);
              }}
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
        <BuiltinAgentForm
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
          <TabsTrigger value="config">{t("builtinAgents.detail.tabs.config")}</TabsTrigger>
          <TabsTrigger value="skills">{t("agents.workspace.skills")}</TabsTrigger>
          <TabsTrigger value="mcpServers">{t("agents.workspace.mcpServers")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <Card>
            <CardContent className="py-6">
              <dl className="grid grid-cols-[10rem_1fr] gap-y-3 text-sm">
                <dt className="text-muted-foreground">{t("builtinAgents.name")}</dt>
                <dd>{agent.name}</dd>
                <dt className="text-muted-foreground">{t("agents.description")}</dt>
                <dd>{agent.description ?? <span className="text-muted-foreground">—</span>}</dd>
                <dt className="text-muted-foreground">{t("builtinAgents.model")}</dt>
                <dd className="font-mono text-xs">{config.model}</dd>
                <dt className="text-muted-foreground">{t("builtinAgents.detail.providerKey")}</dt>
                <dd>
                  {keyConfigured ? (
                    <span className="inline-flex items-center gap-1 text-primary">
                      <Check className="size-3.5" />
                      {t("builtinAgents.detail.keyConfigured", { provider })}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">
                      {t("builtinAgents.detail.keyNotConfigured")}
                    </span>
                  )}
                </dd>
                <dt className="text-muted-foreground">{t("builtinAgents.useGateway")}</dt>
                <dd>{useGateway ? t("common.enabled") : t("common.disabled")}</dd>
                <dt className="text-muted-foreground">{t("builtinAgents.confirmTools")}</dt>
                <dd>
                  {config.confirm_tools && config.confirm_tools.length > 0 ? (
                    <span className="font-mono text-xs">{config.confirm_tools.join(", ")}</span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </dd>
                <dt className="text-muted-foreground">{t("builtinAgents.detail.created")}</dt>
                <dd>{formatDateTime(agent.created_at)}</dd>
                <dt className="text-muted-foreground">{t("builtinAgents.detail.updated")}</dt>
                <dd>{formatDateTime(agent.updated_at)}</dd>
              </dl>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="config" className="pt-6">
          <Card>
            <CardContent className="space-y-4 py-6">
              <dl className="grid grid-cols-[10rem_1fr] gap-y-3 text-sm">
                <dt className="text-muted-foreground">{t("builtinAgents.model")}</dt>
                <dd className="font-mono text-xs">{config.model}</dd>
                <dt className="text-muted-foreground">{t("builtinAgents.credentialRef")}</dt>
                <dd className="font-mono text-xs">
                  {config.credential_ref ?? <span className="text-muted-foreground">—</span>}
                </dd>
              </dl>
              <p className="text-xs text-muted-foreground">
                {t("builtinAgents.detail.modelManagedPrefix")}{" "}
                <Link to="/settings/ai" className="text-primary underline-offset-2 hover:underline">
                  {t("builtinAgents.detail.modelManagedLink")}
                </Link>
                {t("builtinAgents.detail.modelManagedSuffix")}
              </p>
              <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
                <Pencil className="mr-1.5 size-3.5" /> {t("builtinAgents.detail.editBehaviour")}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="skills" className="pt-6">
          <BuiltinAgentSkillsTab agentName={name} useGateway={useGateway} />
        </TabsContent>

        <TabsContent value="mcpServers" className="pt-6">
          <BuiltinAgentMcpServersTab agentName={name} useGateway={useGateway} />
        </TabsContent>
      </Tabs>

      <Dialog
        open={deleteOpen}
        onOpenChange={(o) => {
          if (!o) {
            setDeleteOpen(false);
            setDeleteError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("builtinAgents.removeConfirm", { name })}</DialogTitle>
            <DialogDescription>{t("builtinAgents.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          {deleteError ? (
            <p className="text-sm text-destructive" role="alert">
              {deleteError}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setDeleteOpen(false);
                setDeleteError(null);
              }}
            >
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
                  onError: (err) => setDeleteError(translateApiError(t, err)),
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
