// frontend/src/components/agents/ConfigFileTree.tsx — spec 004.
// Left pane of the agent config viewer: the curated config-file allowlist as
// a "tree". Single files are flat rows; directory-backed keys (kind ===
// "directory") render as expandable nodes whose children come from the list
// response. Selection is read-only navigation — config files are edited in the
// user's own editor, so there is no "new file" affordance. Pure presentation;
// all state lives in AgentConfigFilesEditor.
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder } from "lucide-react";

import type { ConfigFileInfo } from "@/lib/api/agents";
import { cn } from "@/lib/utils";

export interface ConfigFileTreeProps {
  files: ConfigFileInfo[];
  selectedKey: string | null;
  selectedChild: string | null;
  expandedDirs: Record<string, boolean>;
  onSelectFile: (key: string) => void;
  onSelectDirectory: (key: string) => void;
  onSelectChild: (key: string, relpath: string) => void;
}

export function ConfigFileTree({
  files,
  selectedKey,
  selectedChild,
  expandedDirs,
  onSelectFile,
  onSelectDirectory,
  onSelectChild,
}: ConfigFileTreeProps) {
  const { t } = useTranslation();

  return (
    <ul className="space-y-0.5">
      {files.map((f) =>
        f.kind === "directory" ? (
          <li key={f.key}>
            <button
              type="button"
              onClick={() => onSelectDirectory(f.key)}
              aria-expanded={!!expandedDirs[f.key]}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                selectedKey === f.key && !selectedChild
                  ? "bg-primary/10 text-primary"
                  : "hover:bg-secondary hover:text-foreground",
              )}
            >
              {expandedDirs[f.key] ? (
                <ChevronDown className="size-3.5 shrink-0 opacity-70" />
              ) : (
                <ChevronRight className="size-3.5 shrink-0 opacity-70" />
              )}
              <Folder className="size-4 shrink-0 opacity-70" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{f.display_name}</span>
                <span className="block truncate font-mono text-[11px] text-muted-foreground">
                  {f.path}
                </span>
              </span>
            </button>
            {expandedDirs[f.key] ? (
              (f.files ?? []).length === 0 ? (
                <p className="py-1 pl-9 pr-2 text-xs text-muted-foreground">
                  {t("agents.config.emptyDir")}
                </p>
              ) : (
                <ul className="space-y-0.5">
                  {(f.files ?? []).map((c) => (
                    <li key={c.relpath}>
                      <button
                        type="button"
                        onClick={() => onSelectChild(f.key, c.relpath)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-md py-1 pl-9 pr-2 text-left transition-colors",
                          selectedKey === f.key && selectedChild === c.relpath
                            ? "bg-primary/10 text-primary"
                            : "hover:bg-secondary hover:text-foreground",
                        )}
                      >
                        <FileText className="size-3.5 shrink-0 opacity-70" />
                        <span className="min-w-0 flex-1 truncate text-sm">{c.relpath}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </li>
        ) : (
          <li key={f.key}>
            <button
              type="button"
              onClick={() => onSelectFile(f.key)}
              className={cn(
                "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                selectedKey === f.key && !selectedChild
                  ? "bg-primary/10 text-primary"
                  : "hover:bg-secondary hover:text-foreground",
                !f.exists && selectedKey !== f.key && "opacity-55",
              )}
            >
              <FileText className="size-4 shrink-0 opacity-70" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{f.display_name}</span>
                <span className="block truncate font-mono text-[11px] text-muted-foreground">
                  {f.path}
                </span>
              </span>
              {!f.exists ? (
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
                  {t("agents.config.notCreated")}
                </span>
              ) : null}
            </button>
          </li>
        ),
      )}
    </ul>
  );
}
