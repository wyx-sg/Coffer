// frontend/src/components/skills/SkillDetailPane.tsx
// The open skill in the Skills page's reading pane (spec skill-manager "Cover
// skill management on REST, the CLI and the web"): the header, the banners of
// what needs the reader (SkillBanners), and four tabs in this order — Files
// (the default), Delivery, Requires, History (the master folder's
// versions, from the vault's history). The Files tab carries the
// built-in note or a Git skill's Source block above the files, and, when the
// master folder is gone, the two ways forward instead of them. The page owns
// the address (`/skills/<name>/<tab>`); this pane only renders the tab it is
// given. It is loaded on first open (the Files tab pulls in the editor and the
// Markdown pipeline).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

import { SkillBanners } from "@/components/skills/SkillBanners";
import { SkillCopyDialog } from "@/components/skills/SkillCopyDialog";
import { SkillDeliveryTab } from "@/components/skills/SkillDeliveryTab";
import { SkillDetailHeader } from "@/components/skills/SkillDetailHeader";
import { SkillFileTree } from "@/components/skills/SkillFileTree";
import { SkillGitSourcePanel } from "@/components/skills/SkillGitSource";
import { SkillHistoryTab } from "@/components/skills/SkillHistoryTab";
import { SkillMissingMaster } from "@/components/skills/SkillMissingMaster";
import { SkillRequiresTab } from "@/components/skills/SkillRequiresTab";
import { SkillUpdateDialog } from "@/components/skills/SkillUpdateDialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useClis } from "@/lib/hooks/useClis";
import { useSkillCopies } from "@/lib/hooks/useSkills";
import { skillAttention } from "@/lib/skills/attention";
import type { SkillTab } from "@/lib/skills/tabs";

interface Props {
  skill: SkillOut;
  tab: SkillTab;
  onTabChange: (tab: string) => void;
  onDeleted: () => void;
}

export function SkillDetailPane({ skill, tab, onTabChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const copies = useSkillCopies();
  const clis = useClis().data?.items ?? [];
  const [reviewing, setReviewing] = useState<SkillDriftEntry | null>(null);
  const [updating, setUpdating] = useState(false);

  const attention = skillAttention(skill, clis, copies.data?.entries);
  const masterMissing = attention.some((a) => a.kind === "masterMissing");

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SkillDetailHeader skill={skill} masterMissing={masterMissing} onDeleted={onDeleted} />

      <SkillBanners
        skill={skill}
        items={attention}
        onReviewCopy={setReviewing}
        onReviewUpdate={() => setUpdating(true)}
      />

      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
          <TabsTrigger value="delivery">{t("skills.detail.tabs.delivery")}</TabsTrigger>
          <TabsTrigger value="requires">{t("skills.detail.tabs.requires")}</TabsTrigger>
          <TabsTrigger value="history">{t("skills.detail.tabs.history")}</TabsTrigger>
        </TabsList>

        <TabsContent value="files" className="flex flex-col gap-4">
          {masterMissing ? (
            <SkillMissingMaster skill={skill} onDeleted={onDeleted} />
          ) : (
            <>
              {skill.builtin ? (
                <Alert variant="info" data-testid="skill-builtin-banner">
                  <Info aria-hidden />
                  <AlertTitle>{t("skills.detail.builtinBanner.title")}</AlertTitle>
                  <AlertDescription>{t("skills.detail.builtinBanner.body")}</AlertDescription>
                </Alert>
              ) : null}
              {skill.source.type === "git_import" ? <SkillGitSourcePanel skill={skill} /> : null}
              <SkillFileTree uid={skill.uid} owner={skill.name} builtin={skill.builtin} />
            </>
          )}
        </TabsContent>
        <TabsContent value="delivery">
          <SkillDeliveryTab skill={skill} onReview={setReviewing} />
        </TabsContent>
        <TabsContent value="requires">
          <SkillRequiresTab skill={skill} />
        </TabsContent>
        <TabsContent value="history">
          <SkillHistoryTab skill={skill} />
        </TabsContent>
      </Tabs>

      <SkillCopyDialog
        skill={skill}
        entry={reviewing}
        onOpenChange={(open) => !open && setReviewing(null)}
      />
      {skill.source.type === "git_import" ? (
        <SkillUpdateDialog skill={skill} open={updating} onOpenChange={setUpdating} />
      ) : null}
    </div>
  );
}
