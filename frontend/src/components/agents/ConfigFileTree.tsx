// frontend/src/components/agents/ConfigFileTree.tsx — spec 004.
// Left pane of the agent config editor: the curated config-file allowlist as
// a "tree". Single files are flat rows; directory-backed keys (kind ===
// "directory") render as expandable nodes whose children come from the list
// response, plus a per-directory "new file" affordance. Pure presentation —
// all state lives in AgentConfigFilesEditor.
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { cn } from "@/lib/utils";

// Keys that have a human description under `agents.config.desc.<key>`. Listing
// them explicitly keeps an unknown/new key from rendering a raw i18n string.
const DESCRIBED_KEYS = new Set([
  "settings",
  "settings_local",
  "global",
  "instructions",
  "subagents",
  "config",
  "hooks",
]);

export interface ConfigFileTreeProps {
  files: ConfigFileInfo[];
  selectedKey: string | null;
  selectedChild: string | null;
  expandedDirs: Record<string, boolean>;
  onSelectFile: (key: string) => void;
  onSelectDirectory: (key: string) => void;
  onSelectChild: (key: string, relpath: string) => void;
  onNewFile: (dirKey: string) => void;
}

export function ConfigFileTree({
  files,
  selectedKey,
  selectedChild,
  expandedDirs,
  onSelectFile,
  onSelectDirectory,
  onSelectChild,
  onNewFile,
}: ConfigFileTreeProps) {
  const { t } = useTranslation();

  // One-line "what is this file for" description, only for keys we have copy
  // for; unknown keys render nothing rather than a raw i18n key.
  const descFor = (key: string): string | null =>
    DESCRIBED_KEYS.has(key) ? t(`agents.config.desc.${key}`) : null;

  return (
    <ul className="space-y-0.5">
      {files.map((f) =>
        f.kind === "directory" ? (
          <li key={f.key}>
            <div
              className={cn(
                "flex w-full items-center gap-1 rounded-md px-2 py-1.5 transition-colors",
                selectedKey === f.key && !selectedChild
                  ? "bg-primary/10 text-primary"
                  : "hover:bg-secondary hover:text-foreground",
              )}
            >
              <button
                type="button"
                onClick={() => onSelectDirectory(f.key)}
                aria-expanded={!!expandedDirs[f.key]}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
              >
                {expandedDirs[f.key] ? (
                  <ChevronDown className="size-3.5 shrink-0 opacity-70" />
                ) : (
                  <ChevronRight className="size-3.5 shrink-0 opacity-70" />
                )}
                <Folder className="size-4 shrink-0 opacity-70" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">{f.display_name}</span>
                  {descFor(f.key) ? (
                    <span className="block truncate text-xs text-muted-foreground">
                      {descFor(f.key)}
                    </span>
                  ) : null}
                  <span className="block truncate font-mono text-[11px] text-muted-foreground">
                    {f.path}
                  </span>
                </span>
              </button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-6 shrink-0"
                aria-label={t("agents.config.newFile")}
                title={t("agents.config.newFile")}
                onClick={() => onNewFile(f.key)}
              >
                <Plus className="size-3.5" />
              </Button>
            </div>
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
                {descFor(f.key) ? (
                  <span className="block truncate text-xs text-muted-foreground">
                    {descFor(f.key)}
                  </span>
                ) : null}
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
