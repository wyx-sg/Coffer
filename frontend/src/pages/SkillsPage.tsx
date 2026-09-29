// frontend/src/pages/SkillsPage.tsx — spec skill-manager "Cover skill management on REST, the CLI and the web".
// The Skills page is the library beside a reading pane (design add-skill-sources
// decision 8): `/skills`, `/skills/<name>` and `/skills/<name>/<tab>` all render
// it, the list on the left (SkillLibrary) and, on the right, the open skill
// (SkillDetailPane, loaded on first open), what Check copies found
// (SkillCopiesPanel), the first-run state while the library holds nothing of
// the user's own, or a prompt to choose a skill.
//
// Addressing: a skill is addressed by its fixed NAME; the REST API takes the
// uid, which comes from the list row the name resolves to. Old addresses keep
// working — `/skills/<uid>` redirects to the name, `?tab=overview` (the tab
// that became Delivery) to `/delivery`, `?tab=files` to the bare Files address.
import { lazy, Suspense, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, Sparkles } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import { PageHeader } from "@/components/PageHeader";
import { SplitView } from "@/components/SplitView";
import { SkillAddDialog, type SkillAddSource } from "@/components/skills/SkillAddDialog";
import { SkillCopiesPanel } from "@/components/skills/SkillCopiesPanel";
import { SkillFirstRun } from "@/components/skills/SkillFirstRun";
import { SkillLibrary } from "@/components/skills/SkillLibrary";
import { Button } from "@/components/ui/button";
import { translateApiError } from "@/lib/api/errors";
import { canonicalDetailPath, resolveByName, useDetailTab } from "@/lib/detailTabs";
import { useCheckSkillCopies, useSkills } from "@/lib/hooks/useSkills";
import { DEFAULT_SKILL_TAB as DEFAULT_TAB, SKILL_TABS as TABS } from "@/lib/skills/tabs";

const SkillDetailPane = lazy(() =>
  import("@/components/skills/SkillDetailPane").then((m) => ({ default: m.SkillDetailPane })),
);

/** The old Overview tab is Delivery now; every other old `?tab=` maps as is. */
function withOverviewAsDelivery(search: string): string {
  const params = new URLSearchParams(search);
  if (params.get("tab") === "overview") params.set("tab", "delivery");
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function SkillsPage() {
  const { t } = useTranslation();
  const { name: nameParam = "", tab: pathTab } = useParams<{ name?: string; tab?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const list = useSkills();
  const check = useCheckSkillCopies();
  const [addOpen, setAddOpen] = useState(false);
  const [addSource, setAddSource] = useState<SkillAddSource>("folder");
  const [showCopies, setShowCopies] = useState(false);

  const skills = list.data ?? [];
  const match = resolveByName(list.data, nameParam);
  const legacyOverview = new URLSearchParams(location.search).get("tab") === "overview";
  const basePath = `/skills/${encodeURIComponent(nameParam)}`;
  const [tab, setTab] = useDetailTab(TABS, DEFAULT_TAB, basePath, {
    enabled: !!match && !match.byUid && !legacyOverview,
  });

  // An old address: the uid form, or the tab that was renamed. One redirect
  // lands on the canonical form of both at once.
  if (match && (match.byUid || legacyOverview)) {
    return (
      <Navigate
        replace
        state={location.state}
        to={canonicalDetailPath(
          `/skills/${encodeURIComponent(match.item.name)}`,
          pathTab,
          withOverviewAsDelivery(location.search),
          TABS,
          DEFAULT_TAB,
        )}
      />
    );
  }

  const openAdd = (source: SkillAddSource) => {
    setAddSource(source);
    setAddOpen(true);
  };
  const checkCopies = () => {
    setShowCopies(true);
    check.mutate();
  };
  const hrefFor = (name: string) =>
    `/skills/${encodeURIComponent(name)}${tab === DEFAULT_TAB ? "" : `/${tab}`}`;
  const ownSkills = skills.filter((s) => !s.builtin);

  let pane: JSX.Element;
  if (showCopies) {
    pane = (
      <SkillCopiesPanel
        report={check.data}
        checking={check.isPending}
        onCheckAgain={() => check.mutate()}
        onClose={() => setShowCopies(false)}
      />
    );
  } else if (list.error) {
    pane = (
      <EmptyState
        tone="error"
        icon={Sparkles}
        title={t("skills.loadFailed")}
        description={translateApiError(t, list.error)}
        action={
          <Button variant="outline" onClick={() => void list.refetch()}>
            {t("common.retry")}
          </Button>
        }
      />
    );
  } else if (list.isPending) {
    pane = <PageFallback />;
  } else if (match) {
    pane = (
      <Suspense fallback={<PageFallback />}>
        <SkillDetailPane
          skill={match.item}
          tab={tab}
          onTabChange={setTab}
          onDeleted={() => navigate("/skills", { replace: true })}
        />
      </Suspense>
    );
  } else if (nameParam) {
    pane = (
      <EmptyState
        icon={Sparkles}
        title={t("skills.detail.notFound", { name: nameParam })}
        description={t("skills.choose.body")}
      />
    );
  } else if (ownSkills.length === 0) {
    pane = <SkillFirstRun hasBuiltin={skills.length > 0} onAdd={openAdd} />;
  } else {
    pane = (
      <EmptyState
        icon={Sparkles}
        title={t("skills.choose.title")}
        description={t("skills.choose.body")}
      />
    );
  }

  return (
    // Full-bleed like the chat page: Layout pads every page, and this one is a
    // workspace whose two panes each scroll on their own.
    <div className="-mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10">
      <div className="shrink-0 border-b border-border-subtle px-6 pb-4 pt-5">
        <PageHeader
          icon={Sparkles}
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
        defaultListWidth={320}
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        detailClassName="overflow-y-auto"
        list={
          <SkillLibrary
            skills={skills}
            isLoading={list.isPending}
            selectedName={match?.item.name ?? null}
            hrefFor={hrefFor}
            onOpenSkill={() => setShowCopies(false)}
            onCheckCopies={checkCopies}
            checkingCopies={check.isPending}
          />
        }
        detail={<div className="px-7 pb-5 pt-5">{pane}</div>}
      />

      <SkillAddDialog open={addOpen} onOpenChange={setAddOpen} initialSource={addSource} />
    </div>
  );
}
