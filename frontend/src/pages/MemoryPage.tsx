// frontend/src/pages/MemoryPage.tsx — the Memory page: what the person's agents remember
// (spec memory "Show and edit memory on the Memory page", "Tidy memory as one change").
//
// Memory is one Markdown file per topic under `vault/memory/projects/<project>/`,
// which every agent reads at the start of a session and writes with its own file
// tools. The header names the folder and holds Tidy (which hands the Tidy prompt
// to the person's agent) and a ⋯ menu with History and, while scheduled tasks
// are on, Set up periodic tidy… (a scheduled task carrying the same prompt).
// While an agent's tidy is open a line says so. Below, the projects beside the
// open project's topic files (`?scope=`); a file opens in a drawer (`?file=`)
// with Edit and Delete. History (`?history=1`) takes the place of both panes.
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Brain, CalendarClock, History, LoaderCircle } from "lucide-react";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { NothingSelected } from "@/components/ListPaneStates";
import { MemoryDrawer } from "@/components/memory/MemoryDrawer";
import { MemoryHistoryView } from "@/components/memory/MemoryHistoryView";
import { MemoryList } from "@/components/memory/MemoryList";
import { MemoryPageEmpty } from "@/components/memory/MemoryPageEmpty";
import { MemoryScopeList } from "@/components/memory/MemoryScopeList";
import { PageHeader } from "@/components/PageHeader";
import { TaskDialog } from "@/components/scheduled-tasks/TaskDialog";
import { SplitView } from "@/components/SplitView";
import { PAGE_BLEED, PAGE_BLEED_HEAD } from "@/components/shell/pageFrame";
import { ActionMenu } from "@/components/ui/menu";
import { useFeatureEnabled } from "@/lib/hooks/useFeatures";
import { useMemoryState, useMemoryTopics } from "@/lib/hooks/useMemory";
import { defaultProject } from "@/lib/memory/projects";
import { cn } from "@/lib/utils";

export function MemoryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { data: state, isPending, error, refetch } = useMemoryState();
  const scheduling = useFeatureEnabled("scheduled_tasks") === true;
  const [planning, setPlanning] = useState(false);
  const projects = state?.projects ?? [];
  const empty = Boolean(state) && projects.length === 0;
  const history = params.get("history") === "1";

  const scope = params.get("scope") ?? defaultProject(projects);
  const project = projects.find((p) => p.folder === scope) ?? null;
  const topics = useMemoryTopics(project?.folder ?? null);
  const rows = useMemo(() => topics.data ?? [], [topics.data]);

  const openName = params.get("file");
  const openIndex = openName ? rows.findIndex((m) => m.name === openName) : -1;
  const open = openIndex >= 0 ? rows[openIndex] : null;
  const setOpen = (name: string | null) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (scope) next.set("scope", scope);
        if (name) next.set("file", name);
        else next.delete("file");
        return next;
      },
      { replace: name !== null && openName !== null },
    );
  const setHistory = (on: boolean) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (on) next.set("history", "1");
      else next.delete("history");
      next.delete("file");
      return next;
    });

  // A stale `?file=` (deleted, or merged by a tidy) closes the drawer instead of leaving it empty.
  useEffect(() => {
    if (openName && topics.data && openIndex < 0) setOpen(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openName, topics.data, openIndex]);

  const stepping = {
    onPrevious: () => openIndex > 0 && setOpen(rows[openIndex - 1].name),
    onNext: () => openIndex < rows.length - 1 && setOpen(rows[openIndex + 1].name),
    hasPrevious: openIndex > 0,
    hasNext: openIndex >= 0 && openIndex < rows.length - 1,
  };

  let pane: JSX.Element | null = null;
  if (project) {
    pane = (
      <MemoryList
        key={project.folder}
        project={project}
        topics={rows}
        isLoading={topics.isPending}
        onOpen={(m) => setOpen(m.name)}
      />
    );
  } else if (state) {
    pane = <NothingSelected icon={Brain} />;
  }

  let body: JSX.Element;
  if (error) body = <MemoryPageEmpty error={error} onRetry={() => void refetch()} />;
  else if (history) body = <MemoryHistoryView onClose={() => setHistory(false)} />;
  else if (empty) body = <MemoryPageEmpty error={null} onRetry={() => void refetch()} />;
  else
    body = (
      <SplitView
        storageKey="memory.scopes"
        defaultListWidth={260}
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1 border-t border-border-subtle"
        listClassName="bg-surface-sidebar"
        detailClassName="overflow-y-auto"
        list={<MemoryScopeList projects={projects} selected={scope} isLoading={isPending} />}
        detail={<div className="px-7 pb-5 pt-5">{pane}</div>}
      />
    );

  const menu = [
    {
      key: "history",
      label: t("memory.history.menu"),
      description: t("memory.history.menuDescription"),
      icon: History,
      onSelect: () => setHistory(true),
    },
    ...(scheduling
      ? [
          {
            key: "periodic",
            label: t("memory.tidy.periodic"),
            description: t("memory.tidy.periodicDescription"),
            icon: CalendarClock,
            onSelect: () => setPlanning(true),
          },
        ]
      : []),
  ];

  return (
    <div className={cn(PAGE_BLEED, "flex-col")}>
      <div className={cn(PAGE_BLEED_HEAD, "flex shrink-0 flex-col gap-3 pb-4")}>
        <PageHeader
          title={t("memory.title")}
          experimental
          subtitle={
            state ? (
              <span className="font-mono text-xs">
                {t("memory.folder", { path: state.folder_path })}
              </span>
            ) : (
              t("memory.subtitle")
            )
          }
          actions={
            state ? (
              <>
                <AgentHandoff
                  prompt={state.tidy_handoff.prompt}
                  label={t("memory.tidy.button")}
                  help={false}
                />
                <ActionMenu label={t("memory.moreActions")} actions={menu} />
              </>
            ) : null
          }
        />
        {state?.tidy_running ? (
          <p className="flex items-center gap-2 text-xs text-text-muted" role="status">
            <LoaderCircle className="size-3.5 animate-spin" aria-hidden />
            {t("memory.tidy.running")}
          </p>
        ) : null}
      </div>

      {body}

      <MemoryDrawer topic={history ? null : open} onClose={() => setOpen(null)} {...stepping} />
      {state && scheduling ? (
        <TaskDialog
          open={planning}
          onOpenChange={setPlanning}
          draft={{
            name: t("memory.tidy.taskName"),
            prompt: state.tidy_handoff.prompt,
            kind: "weekly",
          }}
          onSaved={(uid) => navigate(`/scheduled-tasks/${encodeURIComponent(uid)}`)}
        />
      ) : null}
    </div>
  );
}
