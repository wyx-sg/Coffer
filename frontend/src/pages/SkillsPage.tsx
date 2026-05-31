// frontend/src/pages/SkillsPage.tsx — spec 005-skill-manager surface.
// Mirrors AgentsPage: PageHeader + welcome/loading/error/grid; the Add-skill
// header action appears only once skills exist — the empty state's welcome
// panel carries the Add call-to-action instead. Verification moved to per-row
// and bulk actions inside SkillsTable.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Sparkles } from "lucide-react";

import { SkillAddDialog } from "@/components/skills/SkillAddDialog";
import { SkillsTable } from "@/components/skills/SkillsTable";
import { SkillWelcomePanel } from "@/components/skills/SkillWelcomePanel";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { translateApiError } from "@/lib/api/errors";
import { useSkills } from "@/lib/hooks/useSkills";

export function SkillsPage() {
  const { t } = useTranslation();
  const { data: skills, isPending, error, refetch } = useSkills();
  const [showAdd, setShowAdd] = useState(false);
  const hasSkills = (skills ?? []).length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Sparkles}
        title={t("skills.title")}
        subtitle={t("skills.subtitle")}
        actions={
          hasSkills ? (
            <Button onClick={() => setShowAdd(true)}>
              <Plus className="mr-1 size-4" /> {t("skills.add")}
            </Button>
          ) : null
        }
      />

      <SkillAddDialog open={showAdd} onOpenChange={setShowAdd} onCreated={() => void refetch()} />

      {isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            {t("common.loading")}
          </CardContent>
        </Card>
      ) : error ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive">{t("skills.loadFailed")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{translateApiError(t, error)}</p>
          </CardContent>
        </Card>
      ) : (skills ?? []).length === 0 ? (
        <SkillWelcomePanel onAddSkill={() => setShowAdd(true)} />
      ) : (
        <SkillsTable skills={skills ?? []} />
      )}
    </div>
  );
}
