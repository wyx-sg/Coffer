// frontend/src/components/agents/ConfigFileTree.tsx — spec agent-registry.
// The tree of the agent's Config files tab (boards 2.1.40–2.1.48): every
// allowlisted config file in one tree, grouped by the folder it lives in — the
// config directory as a folder row, a file kept beside it (`~/.claude.json`)
// at the top level under its own name. A directory entry (`rules`, `agents`)
// is a folder of its files; picking it opens its listing, picking a file opens
// it. A file the agent has not written yet is italic with "not created"; the
// open file carries a dot while it has unsaved edits. Pure presentation; all
// state lives in useConfigEditorState.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FileTree, type FileTreeRow } from "@/components/files/FileTree";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConfigFileInfo } from "@/lib/api/agents";

export interface ConfigFileTreeProps {
  files: ConfigFileInfo[];
  selectedKey: string | null;
  selectedChild: string | null;
  /** The open file has edits that are not saved. */
  dirty?: boolean;
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

export function ConfigFileTree(props: ConfigFileTreeProps) {
  const { t } = useTranslation();
  // Folders (the config directory) the person folded.
  const [foldedFolders, setFoldedFolders] = useState<Set<string>>(new Set());

  const rows: FileTreeRow[] = [];
  for (const [folder, entries] of groupByFolder(props.files)) {
    const short = abbreviateHomePath(folder);
    const home = short === "~";
    const folderOpen = home || !foldedFolders.has(folder);
    if (!home) {
      rows.push({
        key: `folder:${folder}`,
        name: short,
        kind: "folder",
        depth: 0,
        open: folderOpen,
        mono: true,
        title: folder,
      });
    }
    if (!folderOpen) continue;
    const depth = home ? 0 : 1;
    for (const f of entries) {
      const name = baseName(f.path);
      if (f.kind === "directory") {
        const open = !props.collapsed[f.key];
        rows.push({
          key: `dir:${f.key}`,
          name,
          kind: "folder",
          depth,
          open,
          title: f.display_name,
          selected: props.selectedKey === f.key && !props.selectedChild,
        });
        if (open) {
          for (const c of f.files ?? []) {
            const selected = props.selectedKey === f.key && props.selectedChild === c.relpath;
            rows.push({
              key: `child:${f.key}/${c.relpath}`,
              name: c.relpath,
              kind: "file",
              depth: depth + 1,
              selected,
              dirty: selected && props.dirty,
            });
          }
        }
        continue;
      }
      const selected = props.selectedKey === f.key && !props.selectedChild;
      rows.push({
        key: `file:${f.key}`,
        name: home ? `~/${name}` : name,
        kind: "file",
        depth,
        selected,
        missing: !f.exists,
        note: t("agents.config.notCreated"),
        dirty: selected && props.dirty,
        title: f.display_name,
      });
    }
  }

  const activate = (row: FileTreeRow) => {
    const sep = row.key.indexOf(":");
    const kind = row.key.slice(0, sep);
    const rest = row.key.slice(sep + 1);
    if (kind === "folder") {
      setFoldedFolders((prev) => {
        const next = new Set(prev);
        if (next.has(rest)) next.delete(rest);
        else next.add(rest);
        return next;
      });
    } else if (kind === "dir") props.onSelectDirectory(rest);
    else if (kind === "file") props.onSelectFile(rest);
    else {
      const slash = rest.indexOf("/");
      props.onSelectChild(rest.slice(0, slash), rest.slice(slash + 1));
    }
  };

  return <FileTree rows={rows} label={t("agents.configTab.treeLabel")} onActivate={activate} />;
}
