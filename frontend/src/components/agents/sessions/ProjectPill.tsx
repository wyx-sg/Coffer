// src/components/agents/sessions/ProjectPill.tsx — the Sessions list's one filter (board 2.1.52).
//
// A pill that says "Project" and, once one is chosen, which ("Project: Coffer").
// It opens the projects the agent's sessions belong to — read from the listing
// itself, newest first — with "All projects" first. The filter is the project's
// path, exactly, as the listing's `project` parameter takes it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Search } from "lucide-react";

import { projectName } from "@/components/agents/sessions/sessionTime";
import { pillClass } from "@/components/filters/pillStyles";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgentTranscripts } from "@/lib/hooks/useAgentTranscripts";
import { cn } from "@/lib/utils";

/** How many recent sessions the project list is read from. */
const PROJECT_SOURCE = 100;

export function ProjectPill({
  uid,
  value,
  onChange,
}: {
  uid: string;
  value: string | null;
  onChange: (project: string | null) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const recent = useAgentTranscripts(uid, {
    limit: PROJECT_SOURCE,
    sort: "last_activity_at",
    order: "desc",
  });
  const projects = [
    ...new Set(
      (recent.data?.sessions ?? [])
        .map((s) => s.project_path)
        .filter((p): p is string => Boolean(p)),
    ),
  ];
  const needle = query.trim().toLowerCase();
  const shown = needle ? projects.filter((p) => p.toLowerCase().includes(needle)) : projects;
  const choose = (next: string | null) => {
    onChange(next);
    setOpen(false);
  };
  const changeOpen = (next: boolean) => {
    setOpen(next);
    if (!next) setQuery("");
  };

  return (
    <Popover open={open} onOpenChange={changeOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={cn(pillClass(!!value, open), "px-2.5")}>
          <span className={cn(value && "font-label text-text")}>
            {value
              ? t("agents.sessionsTab.projectChosen", { project: projectName(value) ?? value })
              : t("agents.sessionsTab.project")}
          </span>
          <ChevronDown className="size-3.5 text-text-subtle" aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-60 p-1" align="end">
        <label className="mx-0.5 mb-1 mt-0.5 flex h-7 items-center gap-1.5 rounded-md border border-border bg-surface-raised px-2 text-xs text-text focus-within:ring-2 focus-within:ring-focus-ring">
          <Search className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("agents.sessionsTab.searchProjects")}
            aria-label={t("agents.sessionsTab.searchProjects")}
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-text-subtle"
          />
        </label>
        <div
          role="listbox"
          aria-label={t("agents.sessionsTab.project")}
          className="flex max-h-80 flex-col overflow-y-auto"
        >
          {[null, ...shown].map((path) => {
            const selected = path === value;
            return (
              <button
                key={path ?? "all"}
                type="button"
                role="option"
                aria-selected={selected}
                title={path ?? undefined}
                onClick={() => choose(path)}
                className={cn(
                  "flex h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-sm text-text",
                  "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
                  selected && "bg-surface-selected font-label",
                )}
              >
                <span className="min-w-0 flex-1 truncate">
                  {path ? (projectName(path) ?? path) : t("agents.sessionsTab.allProjects")}
                </span>
                {selected ? <Check className="size-3.5 text-accent-text" aria-hidden /> : null}
              </button>
            );
          })}
          {needle && shown.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-text-muted">
              {t("agents.sessionsTab.noProjects")}
            </p>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
