// frontend/src/pages/SkillDetailPage.tsx
// Per-skill detail page (mirrors AgentDetailPage): the shared PageHeader with
// a back link, reach + Delete as actions, and two tabs — Overview and Files (a
// tree + content viewer of the skill's master folder, read-only for a builtin
// skill since Coffer rewrites it at every start). The open tab
// lives in the URL (`?tab=`), so a reload lands on the same tab.
import { useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Sparkles, Trash2 } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { ScopeControl } from "@/components/ScopeControl";
import { SkillOverview } from "@/components/skills/SkillDetailTabs";
import { SkillFileTree } from "@/components/skills/SkillFileTree";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { translateApiError } from "@/lib/api/errors";
import { useRemoveSkill, useSkill } from "@/lib/hooks/useSkills";

export function SkillDetailPage() {
  const { t } = useTranslation();
  const { uid = "" } = useParams<{ uid: string }>();
  const navigate = useNavigate();
  // When navigated here from an agent's Skills tab, location.state carries a
  // return target, so "← back" leads to that agent rather than the list.
  const backState = useLocation().state as { backTo?: string; backLabel?: string } | null;
  const back = backState?.backTo
    ? { to: backState.backTo, label: t("common.backTo", { label: backState.backLabel ?? "" }) }
    : { to: "/skills", label: t("skills.detail.back") };
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "overview";
  const { data: skill, isPending, error } = useSkill(uid);
  const remove = useRemoveSkill();
  const [deleteOpen, setDeleteOpen] = useState(false);

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
        title={t("skills.loadFailed")}
        description={error ? translateApiError(t, error) : undefined}
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
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <SkillOverview skill={skill} />
        </TabsContent>

        <TabsContent value="files" className="pt-6">
          <SkillFileTree uid={skill.uid} builtin={skill.builtin} />
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
