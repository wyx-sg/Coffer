// frontend/src/components/agents/ConfigFileTree.tsx — spec agent-registry
// "Preview an agent's config file read-only".
// The tree of the agent's Config files tab: every allowlisted config file in
// one tree, grouped by the folder it lives in — the config directory as a
// folder row, a file kept beside it (`~/.claude.json`) at the top level under
// its own name. A directory entry (`agents`) is a folder of its files. A file
// the agent has not written yet is italic with "not created" and cannot be
// opened. Pure presentation over the shared FileTree; the selection is the
// caller's.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { FileTree, type FileTreeRow } from "@/components/files/FileTree";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConfigFileInfo } from "@/lib/api/agents";

/** The file a tree row opens: the allowlist key and, under a directory entry, the relpath. */
export interface ConfigSelection {
  key: string;
  child?: string;
}

/** Selection to the `?file=` value: `settings`, or `subagents/team/x.md` for a directory child. */
export function selectionToParam(sel: ConfigSelection): string {
  return sel.child ? `${sel.key}/${sel.child}` : sel.key;
}

export function selectionFromParam(value: string | null): ConfigSelection | null {
  if (!value) return null;
  const slash = value.indexOf("/");
  return slash < 0 ? { key: value } : { key: value.slice(0, slash), child: value.slice(slash + 1) };
}

// Keys with a description under `agents.config.desc.<key>`, shown as the row's
// tooltip. Listing them keeps a new key from rendering a raw i18n string.
const DESCRIBED_KEYS = new Set([
  "settings",
  "settings_local",
  "global",
  "instructions",
  "subagents",
  "config",
  "hooks",
]);

function groupByFolder(files: ConfigFileInfo[]): [string, ConfigFileInfo[]][] {
  const groups = new Map<string, ConfigFileInfo[]>();
  for (const f of files) groups.set(f.folder_path, [...(groups.get(f.folder_path) ?? []), f]);
  return [...groups.entries()];
}

/** Every file that can be previewed, in the order the tree lists them. */
export function openableSelections(files: ConfigFileInfo[]): ConfigSelection[] {
  const out: ConfigSelection[] = [];
  for (const [, entries] of groupByFolder(files)) {
    for (const f of entries) {
      if (f.kind === "directory") {
        for (const c of f.files ?? []) out.push({ key: f.key, child: c.relpath });
      } else if (f.exists) out.push({ key: f.key });
    }
  }
  return out;
}

export function ConfigFileTree({
  files,
  agentName,
  selected,
  onSelect,
}: {
  files: ConfigFileInfo[];
  agentName: string;
  selected: ConfigSelection | null;
  onSelect: (selection: ConfigSelection) => void;
}) {
  const { t } = useTranslation();
  // Folders the person folded: the config directory and directory entries.
  const [folded, setFolded] = useState<Set<string>>(new Set());
  const describe = (f: ConfigFileInfo) =>
    DESCRIBED_KEYS.has(f.key)
      ? `${f.display_name} — ${t(`agents.config.desc.${f.key}`, { agent: agentName })}`
      : f.display_name;

  const rows: FileTreeRow[] = [];
  for (const [folder, entries] of groupByFolder(files)) {
    const short = abbreviateHomePath(folder);
    const home = short === "~";
    const folderOpen = home || !folded.has(`folder:${folder}`);
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
        const children = f.files ?? [];
        const open = !folded.has(`dir:${f.key}`);
        rows.push({
          key: `dir:${f.key}`,
          name,
          kind: "folder",
          depth,
          open,
          leaf: children.length === 0,
          missing: !f.exists,
          note: t("agents.config.notCreated"),
          title: describe(f),
        });
        if (open) {
          for (const c of children) {
            rows.push({
              key: `child:${f.key}/${c.relpath}`,
              name: c.relpath,
              kind: "file",
              depth: depth + 1,
              selected: selected?.key === f.key && selected.child === c.relpath,
              title: c.path,
            });
          }
        }
        continue;
      }
      rows.push({
        key: `file:${f.key}`,
        name: home ? `~/${name}` : name,
        kind: "file",
        depth,
        selected: selected?.key === f.key && !selected.child,
        missing: !f.exists,
        note: t("agents.config.notCreated"),
        title: describe(f),
      });
    }
  }

  const toggle = (id: string) =>
    setFolded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const activate = (row: FileTreeRow) => {
    const sep = row.key.indexOf(":");
    const kind = row.key.slice(0, sep);
    const rest = row.key.slice(sep + 1);
    if (kind === "folder" || kind === "dir") toggle(row.key);
    else if (kind === "file") {
      if (!row.missing) onSelect({ key: rest });
    } else {
      const slash = rest.indexOf("/");
      onSelect({ key: rest.slice(0, slash), child: rest.slice(slash + 1) });
    }
  };

  return <FileTree rows={rows} label={t("agents.configTab.treeLabel")} onActivate={activate} />;
}
