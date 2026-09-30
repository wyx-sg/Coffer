// frontend/src/pages/SkillDetailPage.tsx
// Per-skill detail page (mirrors AgentDetailPage): the shared PageHeader with
// a back link, the skill's name and the fixed-name badge, reach + Delete as
// actions, and three tabs — Overview, Files (a
// tree + content viewer of the skill's master folder, read-only for a builtin
// skill since Coffer rewrites it at every start) and Requires (the commands its
// SKILL.md declares, each linking to its page on the CLIs page). The page is addressed by
// the skill's NAME (fixed at creation, unique among skills) and the open tab
// lives in the path (`/skills/<name>/files`), so a reload lands on the same
// tab. The REST API addresses a skill by uid, so the name is resolved against
// the skills list; an old uid address redirects to the name address.
import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Sparkles, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { FixedNameBadge } from "@/components/resource/FixedName";
import { SkillOverview } from "@/components/skills/SkillDetailTabs";
import { SkillFileTree } from "@/components/skills/SkillFileTree";
import { SkillRequiresTab } from "@/components/skills/SkillRequiresTab";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { canonicalDetailPath, resolveByName, useDetailTab } from "@/lib/detailTabs";
import { useRemoveSkill, useSkill, useSkills } from "@/lib/hooks/useSkills";

const TABS = ["overview", "files", "requires"] as const;

export function SkillDetailPage() {
  const { t } = useTranslation();
  const { name: nameParam = "", tab: pathTab } = useParams<{ name: string; tab?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  // When navigated here from an agent's Skills tab, location.state carries a
  // return target, so "← back" leads to that agent rather than the list.
  const backState = location.state as { backTo?: string; backLabel?: string } | null;
  const back = backState?.backTo
    ? { to: backState.backTo, label: t("common.backTo", { label: backState.backLabel ?? "" }) }
    : { to: "/skills", label: t("skills.detail.back") };
  const list = useSkills();
  const match = resolveByName(list.data, nameParam);
  const uid = match?.item.uid ?? "";
  const { data: skill, isPending, error } = useSkill(uid);
  const remove = useRemoveSkill();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const basePath = `/skills/${encodeURIComponent(nameParam)}`;
  const [tab, setTab] = useDetailTab(TABS, "overview", basePath, {
    enabled: !!match && !match.byUid,
  });

  // An old uid address: go to the same tab of the name address.
  if (match?.byUid) {
    return (
      <Navigate
        replace
        state={location.state}
        to={canonicalDetailPath(
          `/skills/${encodeURIComponent(match.item.name)}`,
          pathTab,
          location.search,
          TABS,
          "overview",
        )}
      />
    );
  }

  if (list.isPending || (!!uid && isPending)) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }
  if (list.error || error || !skill) {
    const failure = list.error ?? error;
    return (
      <EmptyState
        icon={Sparkles}
        title={t("skills.loadFailed")}
        description={failure ? translateApiError(t, failure) : undefined}
        action={
          <Button variant="outline" asChild>
            <Link to="/skills">
              <ArrowLeft className="mr-1 size-4" />
              {t("skills.detail.back")}
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* The description is long-form and lives in the Overview card, not the
          subtitle — a paragraph under the title pushed the tabs off-screen. */}
      <PageHeader
        back={back}
        title={skill.name}
        badges={<FixedNameBadge />}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <ScopeControl kind="skill" uid={skill.uid} enabled={skill.enabled} />
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

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">{t("skills.detail.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
          <TabsTrigger value="requires">{t("skills.detail.tabs.requires")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <SkillOverview skill={skill} />
        </TabsContent>

        <TabsContent value="files" className="pt-6">
          <SkillFileTree uid={skill.uid} builtin={skill.builtin} />
        </TabsContent>

        <TabsContent value="requires" className="pt-6">
          <SkillRequiresTab skillUid={skill.uid} />
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("skills.removeConfirmTitle", { name: skill.name })}
        description={t("skills.removeConfirmBody")}
        confirmLabel={remove.isPending ? t("common.deleting") : t("common.delete")}
        pending={remove.isPending}
        onConfirm={() =>
          // Close only on success; the hook toasts a failure.
          remove.mutate(skill.uid, {
            onSuccess: () => {
              setDeleteOpen(false);
              navigate("/skills");
            },
          })
        }
      />
    </div>
  );
}
