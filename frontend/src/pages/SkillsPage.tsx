// frontend/src/pages/SkillsPage.tsx — spec skill-manager "Cover skill management on REST and the web".
// The Skills page is the library beside a reading pane (design add-skill-sources
// decision 8): `/skills`, `/skills/<name>` and `/skills/<name>/<tab>` all render
// it, the list on the left (SkillLibrary) and, on the right, what
// SkillsReadingPane picks — Check copies, the selection, the open skill, the
// first run or a prompt to choose a skill.
//
// Addressing: a skill is addressed by its fixed NAME; the REST API takes the
// uid, which comes from the list row the name resolves to.
import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { SkillAddDialog, type SkillAddSource } from "@/components/skills/SkillAddDialog";
import { SkillLibrary } from "@/components/skills/SkillLibrary";
import { SkillsReadingPane } from "@/components/skills/SkillsReadingPane";
import { Button } from "@/components/ui/button";
import { useDetailTab } from "@/lib/detailTabs";
import { useSkillCopies, useSkills } from "@/lib/hooks/useSkills";
import { DEFAULT_SKILL_TAB as DEFAULT_TAB, SKILL_TABS as TABS } from "@/lib/skills/tabs";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { cn } from "@/lib/utils";

export function SkillsPage() {
  const { t } = useTranslation();
  const { name: nameParam = "" } = useParams<{ name?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const list = useSkills();
  const copies = useSkillCopies();
  const [addOpen, setAddOpen] = useState(false);
  const [addSource, setAddSource] = useState<SkillAddSource>("folder");
  const [showCopies, setShowCopies] = useState(false);
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());

  const skills = list.data ?? [];
  const match = nameParam ? skills.find((s) => s.name === nameParam) : undefined;
  const orphan = nameParam ? null : new URLSearchParams(location.search).get("orphan");
  const basePath = `/skills/${encodeURIComponent(nameParam)}`;
  const [tab, setTab] = useDetailTab(TABS, DEFAULT_TAB, basePath, { enabled: !!match });

  const openAdd = (source: SkillAddSource) => {
    setAddSource(source);
    setAddOpen(true);
  };
  const checkCopies = () => {
    setShowCopies(true);
    void copies.refetch();
  };
  const hrefFor = (name: string) =>
    `/skills/${encodeURIComponent(name)}${tab === DEFAULT_TAB ? "" : `/${tab}`}`;
  // A selection only ever holds rows that still exist and can be deleted.
  const selected = skills.filter((s) => !s.builtin && picked.has(s.uid));
  const clearSelection = () => setPicked(new Set());

  const reading = (onDeleted: () => void) => (
    <SkillsReadingPane
      list={list}
      skills={skills}
      match={match ?? null}
      nameParam={nameParam}
      orphan={orphan}
      tab={tab}
      onTabChange={setTab}
      showCopies={showCopies}
      onCloseCopies={() => setShowCopies(false)}
      selected={selected}
      onClearSelection={clearSelection}
      onAdd={openAdd}
      onCheckCopies={checkCopies}
      onDeleted={onDeleted}
    />
  );

  return (
    // Full-bleed like the chat page: Layout pads every page, and this one is a
    // workspace whose two panes each scroll on their own.
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "shrink-0 pb-3")}>
        <PageHeader
          title={t("skills.title")}
          subtitle={t("skills.subtitle")}
          actions={
            <Button onClick={() => openAdd("folder")}>
              <Plus aria-hidden /> {t("skills.add")}
            </Button>
          }
        />
      </div>

      <SplitView
        storageKey="skills.list"
        defaultListWidth={300}
        listMinWidth={180}
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        detailClassName="overflow-y-auto"
        list={
          <SkillLibrary
            skills={skills}
            isLoading={list.isPending}
            error={list.error}
            onRetry={() => void list.refetch()}
            selectedName={match?.name ?? null}
            hrefFor={hrefFor}
            onOpenSkill={() => setShowCopies(false)}
            onCheckCopies={checkCopies}
            checkingCopies={copies.isFetching}
            drift={copies.data?.entries}
            picked={picked}
            onPickedChange={setPicked}
            selected={selected}
            orphan={orphan}
          />
        }
        detail={
          <div className="px-7 pb-5 pt-5">
            {reading(() => navigate("/skills", { replace: true }))}
          </div>
        }
      />

      <SkillAddDialog open={addOpen} onOpenChange={setAddOpen} initialSource={addSource} />
    </div>
  );
}
