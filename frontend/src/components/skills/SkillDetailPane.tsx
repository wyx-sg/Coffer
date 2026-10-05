// frontend/src/components/skills/SkillDetailPane.tsx
// The open skill in the Skills page's reading pane (spec skill-manager "Manage
// skills on REST and on the Skills page", canvas 4.3 SkillHeader): the header,
// the tab strip — Files (the default), Delivery, Requires, History, never with
// counts — and, under the strip, the banners of what needs the
// reader. Banners are split by owner: the master folder (SkillMasterBanner) and
// what the skill depends on (SkillDependencyBanners) are drawn here, the Git
// source's and the copies' are SkillBanners'. The Files tab carries a Git
// skill's Source block above the files, or — when the master folder is gone —
// an empty state saying there are no files. History is the master folder's
// versions from the vault's history (SkillHistoryTab). The page owns the address
// (`/skills/<name>/<tab>`); this pane only renders the tab it is given. It is
// loaded on first open (the Files tab pulls in the Markdown
// pipeline).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { SkillBanners } from "@/components/skills/SkillBanners";
import { SkillCopyDialog } from "@/components/skills/SkillCopyDialog";
import { SkillDependencyBanners } from "@/components/skills/SkillDependencyBanners";
import { SkillDeliveryTab } from "@/components/skills/SkillDeliveryTab";
import { SkillDetailHeader } from "@/components/skills/SkillDetailHeader";
import { SkillFileTree } from "@/components/skills/SkillFileTree";
import { SkillGitSourcePanel } from "@/components/skills/SkillGitSource";
import { SkillHistoryTab } from "@/components/skills/SkillHistoryTab";
import { SkillMasterBanner } from "@/components/skills/SkillMasterBanner";
import { SkillMissingMaster } from "@/components/skills/SkillMissingMaster";
import { SkillRequiresTab } from "@/components/skills/SkillRequiresTab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SkillDriftEntry, SkillOut } from "@/lib/api/skills";
import { useClis } from "@/lib/hooks/useClis";
import { useSkillCopies } from "@/lib/hooks/useSkills";
import { skillAttention, skillStatus } from "@/lib/skills/attention";
import type { SkillTab } from "@/lib/skills/tabs";

interface Props {
  skill: SkillOut;
  tab: SkillTab;
  onTabChange: (tab: string) => void;
  onDeleted: () => void;
}

/** The attention kinds this pane draws itself; SkillBanners draws the rest. */
const OWN_KINDS = new Set(["masterMissing", "requires", "toolOff", "secrets"]);

export function SkillDetailPane({ skill, tab, onTabChange, onDeleted }: Props) {
  const { t } = useTranslation();
  const copies = useSkillCopies();
  const clis = useClis().data?.items ?? [];
  const [reviewing, setReviewing] = useState<SkillDriftEntry | null>(null);

  const attention = skillAttention(skill, clis, copies.data?.entries);
  const masterMissing = attention.some((a) => a.kind === "masterMissing");
  const rest = attention.filter((a) => !OWN_KINDS.has(a.kind));

  return (
    <div className="flex min-w-0 flex-col gap-[18px]">
      <SkillDetailHeader
        skill={skill}
        status={skillStatus(skill, attention)}
        onDeleted={onDeleted}
      />

      <Tabs value={tab} onValueChange={onTabChange}>
        <TabsList>
          <TabsTrigger value="files">{t("skills.detail.tabs.files")}</TabsTrigger>
          <TabsTrigger value="delivery">{t("skills.detail.tabs.delivery")}</TabsTrigger>
          <TabsTrigger value="requires">{t("skills.detail.tabs.requires")}</TabsTrigger>
          <TabsTrigger value="history">{t("skills.detail.tabs.history")}</TabsTrigger>
        </TabsList>

        {attention.length > 0 ? (
          <div className="mt-4 flex flex-col gap-2.5">
            {masterMissing ? <SkillMasterBanner skill={skill} onDeleted={onDeleted} /> : null}
            <SkillDependencyBanners skill={skill} items={attention} />
            <SkillBanners skill={skill} items={rest} onReviewCopy={setReviewing} />
          </div>
        ) : null}

        <TabsContent value="files" className="flex flex-col gap-4">
          {masterMissing ? (
            <SkillMissingMaster />
          ) : (
            <>
              {skill.source.type === "git_import" ? <SkillGitSourcePanel skill={skill} /> : null}
              <SkillFileTree uid={skill.uid} owner={skill.name} builtin={skill.builtin} />
            </>
          )}
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

      <SkillCopyDialog
        skill={skill}
        entry={reviewing}
        onOpenChange={(open) => !open && setReviewing(null)}
      />
    </div>
  );
}
