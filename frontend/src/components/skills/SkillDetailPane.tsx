// frontend/src/components/skills/SkillDetailPane.tsx
// The open skill in the Skills page's reading pane (spec skill-manager "Cover
// skill management on REST, the CLI and the web"): the header, the built-in
// banner or the Git source panel where they apply, and four tabs in this
// order — Files (the default), Delivery, Requires, History (the master
// folder's versions, from the vault's history). The page owns the
// address (`/skills/<name>/<tab>`); this pane only renders the tab it is
// given. It is loaded on first open (SkillsPage lazy-loads it), because the
// Files tab pulls in the editor and the Markdown pipeline.
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { SkillDeliveryTab } from "@/components/skills/SkillDeliveryTab";
import { SkillDetailHeader } from "@/components/skills/SkillDetailHeader";
import { SkillFileTree } from "@/components/skills/SkillFileTree";
import { SkillGitSourcePanel } from "@/components/skills/SkillGitSource";
import { SkillHistoryTab } from "@/components/skills/SkillHistoryTab";
import { SkillRequiresTab } from "@/components/skills/SkillRequiresTab";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SkillOut } from "@/lib/api/skills";
import type { SkillTab } from "@/lib/skills/tabs";

interface Props {
  skill: SkillOut;
  tab: SkillTab;
  onTabChange: (tab: string) => void;
  onDeleted: () => void;
}

export function SkillDetailPane({ skill, tab, onTabChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const requires = skill.requires.length;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SkillDetailHeader skill={skill} onDeleted={onDeleted} />

      {skill.builtin ? (
        <Alert variant="info" data-testid="skill-builtin-banner">
          <Info aria-hidden />
          <AlertTitle>{t("skills.detail.builtinBanner.title")}</AlertTitle>
          <AlertDescription>{t("skills.detail.builtinBanner.body")}</AlertDescription>
        </Alert>
      ) : null}

      {skill.source.type === "git_import" ? <SkillGitSourcePanel skill={skill} /> : null}

      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
          <TabsTrigger value="delivery">{t("skills.detail.tabs.delivery")}</TabsTrigger>
          <TabsTrigger value="requires">
            {t("skills.detail.tabs.requires")}
            {requires > 0 ? (
              <span className="text-text-muted" aria-hidden>
                · {requires}
              </span>
            ) : null}
          </TabsTrigger>
          <TabsTrigger value="history">{t("skills.detail.tabs.history")}</TabsTrigger>
        </TabsList>

        <TabsContent value="files">
          <SkillFileTree uid={skill.uid} builtin={skill.builtin} />
        </TabsContent>
        <TabsContent value="delivery">
          <SkillDeliveryTab skill={skill} />
        </TabsContent>
        <TabsContent value="requires">
          <SkillRequiresTab skill={skill} />
        </TabsContent>
        <TabsContent value="history">
          <SkillHistoryTab skill={skill} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
