// frontend/src/components/agents/ConfigFileTree.tsx — spec agent-registry.
// Left pane of the agent's Config files tab: every allowlisted config file in
// one list, grouped by the directory it lives in (the config directory first,
// then `~ (home)` for a file kept beside it), so the instructions files sit
// beside the settings files. Each row is the file's own name and what it is for
// (Settings, Instructions, Subagents…), or "not created" for one the agent has
// not written yet. A directory entry lists its files under it; picking one
// opens it. Pure presentation; all state lives in useConfigEditorState.
import { useTranslation } from "react-i18next";
import { FileText, Folder } from "lucide-react";

import { FILE_PANE_SCROLL } from "@/components/filePane";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { cn } from "@/lib/utils";

/** Keys with a role label under `agents.configTab.role.<key>`. */
const ROLE_KEYS = new Set([
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
  /** Directory keys the user folded. */
  collapsed: Record<string, boolean>;
  onSelectFile: (key: string) => void;
  onSelectDirectory: (key: string) => void;
  onSelectChild: (key: string, relpath: string) => void;
}

function groupByFolder(files: ConfigFileInfo[]): [string, ConfigFileInfo[]][] {
  const groups = new Map<string, ConfigFileInfo[]>();
  for (const f of files) groups.set(f.folder_path, [...(groups.get(f.folder_path) ?? []), f]);
  return [...groups.entries()];
}

const ROW =
  "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition-colors";

export function ConfigFileTree(props: ConfigFileTreeProps) {
  const { t } = useTranslation();
  const role = (f: ConfigFileInfo) =>
    ROLE_KEYS.has(f.key) ? t(`agents.configTab.role.${f.key}`) : f.display_name;
  const rowClass = (selected: boolean) =>
    cn(ROW, selected ? "bg-surface-selected text-text" : "hover:bg-surface-hover hover:text-text");

  return (
    <div className={cn("space-y-3", FILE_PANE_SCROLL)}>
      {groupByFolder(props.files).map(([folder, entries]) => {
        const short = abbreviateHomePath(folder);
        return (
          <section key={folder} className="space-y-0.5">
            <p className="break-all px-2 font-mono text-2xs text-text-subtle">
              {short === "~" ? t("agents.configTab.home") : short}
            </p>
            <ul className="space-y-0.5">
              {entries.map((f) => {
                const isDir = f.kind === "directory";
                const open = isDir && !props.collapsed[f.key];
                const selected = props.selectedKey === f.key && !props.selectedChild;
                return (
                  <li key={f.key}>
                    <button
                      type="button"
                      title={f.display_name}
                      aria-expanded={isDir ? open : undefined}
                      onClick={() =>
                        isDir ? props.onSelectDirectory(f.key) : props.onSelectFile(f.key)
                      }
                      className={rowClass(selected)}
                    >
                      {isDir ? (
                        <Folder className="size-3.5 shrink-0 text-text-muted" aria-hidden />
                      ) : (
                        <FileText className="size-3.5 shrink-0 text-text-muted" aria-hidden />
                      )}
                      <span
                        className={cn(
                          "min-w-0 flex-1 break-all font-mono text-xs",
                          !f.exists && "text-text-muted",
                        )}
                      >
                        {isDir ? `${baseName(f.path)}/` : baseName(f.path)}
                      </span>
                      <span className="shrink-0 text-2xs text-text-subtle">
                        {f.exists ? role(f) : t("agents.config.notCreated")}
                      </span>
                    </button>
                    {open && (f.files ?? []).length > 0 ? (
                      <ul className="space-y-0.5">
                        {(f.files ?? []).map((c) => (
                          <li key={c.relpath}>
                            <button
                              type="button"
                              onClick={() => props.onSelectChild(f.key, c.relpath)}
                              className={cn(
                                rowClass(
                                  props.selectedKey === f.key && props.selectedChild === c.relpath,
                                ),
                                "pl-7",
                              )}
                            >
                              <span className="min-w-0 flex-1 break-all font-mono text-xs">
                                {c.relpath}
                              </span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
