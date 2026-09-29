// frontend/src/pages/UnmanagedSkillDetailPage.tsx — spec skill-manager
// "Preview an unmanaged skill read-only".
// One unmanaged skill — a skill-shaped folder in an agent's own skill locations
// that Coffer does not manage — reached by clicking its row on the agent's
// Skills tab. The same shape as a managed skill's detail page (SkillDetailPage):
// Overview and Files tabs, the open tab in `?tab=`. Everything here reads;
// the header's actions are the ones that change something (open the folder,
// adopt it, delete it).
//
// The folder has no resource row and so no uid: it is addressed the way the
// list and the routes address it, by the agent's uid, the scan location and the
// folder name. The back link is derived from the agent uid in the path rather
// than carried in navigation state, so a reload or a shared link still leads
// back to that agent's Skills tab.
import { Link, useParams, useSearchParams } from "react-router-dom";
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
import { useAgent } from "@/lib/hooks/useAgents";
import { useUnmanagedSkill } from "@/lib/hooks/useUnmanagedSkill";

export function UnmanagedSkillDetailPage() {
  const { t } = useTranslation();
  const { uid = "", location = "", name = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const agent = useAgent(uid);
  const { data: skill, isPending, error } = useUnmanagedSkill(uid, location, name);

  const back = {
    to: `/agents/${encodeURIComponent(uid)}?tab=skills`,
    label: t("common.backTo", { label: agent.data?.name ?? t("agents.workspace.skills") }),
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
  if (error || !skill) {
    return (
      <EmptyState
        icon={Sparkles}
        title={t("agents.skillsTab.unmanagedDetail.notFound")}
        description={error ? translateApiError(t, error) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to={back.to}>
              <ArrowLeft className="mr-1 size-4" />
              {back.label}
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={skill.name}
        badges={<UnmanagedSkillBadges skill={skill} />}
        actions={<UnmanagedSkillActions agentUid={uid} skill={skill} backTo={back.to} />}
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
