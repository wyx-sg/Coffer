// frontend/src/pages/BuiltinAgentDetailPage.tsx
//
// Detail page for the built-in Coffer Assistant (spec 008). It is not a
// registry agent, so it differs from the coding-agent detail: no config-dir /
// config files / plugins / delete. It shows which model it runs on, the master
// skills it can load, and the registered MCP servers whose tools it aggregates.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChatAgents } from "@/lib/hooks/useChatAgents";
import { useModels } from "@/lib/hooks/useModels";
import { useResources } from "@/lib/hooks/useResources";
import { useSkills } from "@/lib/hooks/useSkills";

export function BuiltinAgentDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: chatAgents } = useChatAgents();
  const { data: models = [] } = useModels();
  const { data: skills = [] } = useSkills();
  const { data: mcpServers = [] } = useResources("mcp_server");

  const builtin = (chatAgents ?? []).find((a) => a.agent_key === "builtin");
  const name = builtin?.display_name ?? "Coffer Assistant";
  const defaultModel = models.find((m) => m.is_default) ?? models[0];

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/agents")}>
        <ArrowLeft className="mr-1 size-4" />
        {t("agents.detail.back")}
      </Button>

      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-primary/10 p-2">
          <Sparkles className="size-5 text-primary" strokeWidth={1.75} />
        </div>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            {name}
            <Badge variant="secondary">{t("agents.builtin.badge")}</Badge>
          </h1>
          <p className="text-sm text-muted-foreground">{t("agents.builtin.tagline")}</p>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t("agents.workspace.overview")}</TabsTrigger>
          <TabsTrigger value="skills">{t("agents.workspace.skills")}</TabsTrigger>
          <TabsTrigger value="mcp">{t("agents.mcp.title")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("agents.builtin.detail.modelTitle")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {defaultModel ? (
                <p>
                  {t("agents.builtin.detail.usesModel")}{" "}
                  <span className="font-medium">{defaultModel.display_name}</span>{" "}
                  <span className="text-muted-foreground">
                    ({defaultModel.provider} · {defaultModel.model})
                  </span>
                </p>
              ) : (
                <p className="text-amber-600">{t("agents.builtin.detail.noModel")}</p>
              )}
              <Button variant="secondary" size="sm" onClick={() => navigate("/settings/models")}>
                {t("agents.builtin.detail.configureModels")}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="skills" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("agents.builtin.detail.skillsTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-muted-foreground">
                {t("agents.builtin.detail.skillsNote")}
              </p>
              {skills.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("agents.builtin.detail.none")}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {skills.map((s) => (
                    <Badge key={s.name} variant="outline">
                      {s.name}
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="mcp" className="pt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("agents.builtin.detail.mcpTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-sm text-muted-foreground">
                {t("agents.builtin.detail.mcpNote")}
              </p>
              {mcpServers.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("agents.builtin.detail.none")}</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {mcpServers.map((s) => (
                    <li key={s.name} className="flex items-center gap-2">
                      <span className="font-medium">{s.name}</span>
                      {!s.enabled && (
                        <Badge variant="outline" className="text-muted-foreground">
                          {t("agents.builtin.detail.disabled")}
                        </Badge>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
