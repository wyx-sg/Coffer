// frontend/src/components/agents/BuiltinAgentSection.tsx
// The built-in Coffer Assistant is not a registry agent — it has no config
// dir, config files, MCP-install, or delete; it is configured by a model and
// runs in-process. Its columns therefore differ entirely from the managed
// coding agents, so it gets its own section rather than a special-cased row in
// the managed-agents table.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessageSquare, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useModels } from "@/lib/hooks/useModels";
import { useSkills } from "@/lib/hooks/useSkills";

export function BuiltinAgentSection({ builtin }: { builtin: { display_name: string } }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: models = [] } = useModels();
  const { data: skills = [] } = useSkills();
  const defaultModel = models.find((m) => m.is_default) ?? models[0];

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-muted-foreground">
        {t("agents.builtin.sectionTitle")}
      </h2>
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <div className="rounded-lg bg-primary/10 p-2">
          <Sparkles className="size-5 text-primary" strokeWidth={1.75} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{builtin.display_name}</span>
            <Badge variant="secondary">{t("agents.builtin.badge")}</Badge>
          </div>
          <p className="truncate text-sm text-muted-foreground">
            {defaultModel
              ? t("agents.builtin.runsOn", { model: defaultModel.display_name })
              : t("agents.builtin.detail.noModel")}
          </p>
        </div>
        <div className="hidden items-center gap-2 sm:flex">
          <span className="text-xs text-muted-foreground">{t("agents.cofferSkills")}</span>
          <Badge variant="secondary">{skills.length}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => navigate("/agents/builtin")}>
            {t("agents.builtin.details")}
          </Button>
          <Button size="sm" onClick={() => navigate("/chat")}>
            <MessageSquare className="mr-1.5 size-3.5" />
            {t("agents.builtin.startChat")}
          </Button>
        </div>
      </Card>
    </section>
  );
}
