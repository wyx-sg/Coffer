// frontend/src/pages/SkillDetailPage.tsx
// Per-skill detail page (mirrors AgentDetailPage): a back link, a header with
// the source badge + Delete, and two tabs — Overview and Files (a read-only
// tree + content viewer of the skill's master folder).
import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Trash2 } from "lucide-react";

import { SkillOverview } from "@/components/skills/SkillDetailTabs";
import { SkillFileTree } from "@/components/skills/SkillFileTree";
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
import { useRemoveSkill, useSkill } from "@/lib/hooks/useSkills";

export function SkillDetailPage() {
  const { t } = useTranslation();
  const { name = "" } = useParams<{ name: string }>();
  const navigate = useNavigate();
  // When navigated here from an agent's Skills tab, location.state carries a
  // return target so we can offer a "back to <agent>" button.
  const backState = useLocation().state as { backTo?: string; backLabel?: string } | null;
  const { data: skill, isPending, error } = useSkill(name);
  const remove = useRemoveSkill();
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
  if (error || !skill) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive">{t("skills.loadFailed")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            {error ? translateApiError(t, error) : t("skills.loadFailed")}
          </p>
          <Button variant="link" onClick={() => navigate("/skills")} className="-ml-2">
            <ArrowLeft className="mr-1 size-4" />
            {t("skills.detail.back")}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="-ml-2 flex flex-wrap items-center gap-1">
        {backState?.backTo ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(backState.backTo!)}
            className="text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="mr-1.5 size-4" />
            {t("common.backTo", { label: backState.backLabel ?? "" })}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/skills")}
          className="text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-1.5 size-4" /> {t("skills.detail.back")}
        </Button>
      </div>

      <div className="space-y-2">
        {/* Title + actions on one row; the description sits below the title. */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="font-serif text-3xl tracking-tight">{skill.name}</h1>
            <Badge variant="secondary">{skill.source.type}</Badge>
          </div>
          <div className="flex items-center gap-2">
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
        {skill.description ? (
          <p className="max-w-prose text-sm text-muted-foreground">{skill.description}</p>
        ) : null}
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t("skills.detail.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-6">
          <SkillOverview skill={skill} />
        </TabsContent>

        <TabsContent value="files" className="pt-6">
          <SkillFileTree name={skill.name} />
        </TabsContent>
      </Tabs>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("skills.removeConfirmTitle", { name: skill.name })}</DialogTitle>
            <DialogDescription>{t("skills.removeConfirmBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(skill.name, {
                  onSuccess: () => {
                    setDeleteOpen(false);
                    navigate("/skills");
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
