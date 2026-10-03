// src/pages/UnmanagedSkillDetailPage.tsx — one skill folder Coffer does not manage, at /agents/:type/skills/unmanaged/:location/:name.
//
// Spec skill-manager "Preview an unmanaged skill read-only" and "Act on an
// unmanaged skill from its detail page". Reached from the name on the agent's
// Skills tab; the same shape as a managed skill's page (Overview and Files
// tabs, the open tab in `?tab=`). Everything here reads; the header's actions
// change something (open the folder, adopt it, delete it). The folder has no
// uid: it is addressed by the agent's type, the scan location and the folder
// name, and the way back is the agent's Skills tab.
import { Link, useParams } from "react-router-dom";

import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Sparkles } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import {
  UnmanagedSkillActions,
  UnmanagedSkillBadges,
  UnmanagedSkillInvalidNotice,
  UnmanagedSkillOverview,
} from "@/components/skills/UnmanagedSkillDetailParts";
import { UnmanagedSkillFiles } from "@/components/skills/UnmanagedSkillFiles";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { agentTabPath } from "@/lib/agents/routes";
import { useAgentRoute } from "@/lib/hooks/useAgentRoute";
import { useUnmanagedSkill } from "@/lib/hooks/useUnmanagedSkill";

export function UnmanagedSkillDetailPage() {
  const { t } = useTranslation();
  const { location = "", name = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const route = useAgentRoute();
  const uid = route.uid;
  const { data: skill, isPending: skillPending, error } = useUnmanagedSkill(uid, location, name);
  const isPending = route.isPending || (uid !== "" && skillPending);

  const parent = {
    to: route.type ? agentTabPath(route.type, "skills") : "/agents",
    label: t("agents.workspace.skills"),
  };

  const setTab = (next: string) =>
    setParams(
      (prev) => {
        if (next === "overview") prev.delete("tab");
        else prev.set("tab", next);
        return prev;
      },
      { replace: true },
    );

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (error || route.error || !skill) {
    return (
      <EmptyState
        icon={Sparkles}
        title={t("agents.skillsTab.unmanagedDetail.notFound")}
        description={error || route.error ? translateApiError(t, error ?? route.error) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to={parent.to}>
              <ArrowLeft className="mr-1 size-4" />
              {parent.label}
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={skill.name}
        badges={<UnmanagedSkillBadges skill={skill} />}
        actions={
          <UnmanagedSkillActions
            agentUid={uid}
            skill={skill}
            backTo={parent.to}
          />
        }
      />

      {!skill.valid ? <UnmanagedSkillInvalidNotice reason={skill.reason} /> : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("skills.detail.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <UnmanagedSkillOverview skill={skill} />
        </TabsContent>

        <TabsContent value="files" className="pt-6">
          <UnmanagedSkillFiles agentUid={uid} location={location} name={name} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
