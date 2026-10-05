// frontend/src/components/skills/SkillFileSplit.tsx
// The Files card every skill folder is browsed in (canvas 4.3.01, 4.3.12,
// Foundations 0.6.04): the shared file browser (FileBrowserFrame, with a
// draggable divider) — the folder as the shared file tree under its 36px header
// strip (the skill's name, a lock when the folder is read-only, Reveal in
// Finder) and the open file on the right. No root row: SKILL.md first, then
// folders, then the other files; folders in the sans face, files in mono. In
// a locked folder every file wears a lock. The managed skill (SkillFileTree) and the read-only
// folders (SkillReadOnlyFiles — an unmanaged skill, a folder not in the
// library) are this same card; only the file pane differs.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { FileBrowserFrame } from "@/components/files/FileBrowserFrame";
import { FileTree, FileTreePanel, type FileTreeRow } from "@/components/files/FileTree";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useFsActions } from "@/lib/fsActions";
import { sortSkillNodes } from "@/lib/skills/tree";

// The card's own bounds: the tree may shrink to 160px, the open file keeps 320px.
const SKILL_TREE_MIN = 160;
const SKILL_FILE_MIN = 320;

/** The tree query's state, whichever route it came from. */
export interface SkillFileTreeQuery {
  isPending: boolean;
  error: unknown;
  data: SkillFileNode | undefined;
}

interface Props {
  /** The folder's name, over the tree. */
  name: string;
  tree: SkillFileTreeQuery;
  selected: string;
  onSelect: (path: string) => void;
  /** The folder's absolute path, for Reveal in Finder; falls back to the tree's own. */
  folderPath?: string | null;
  /** Why the folder is locked ("Written by Coffer — read-only"); absent for a folder Coffer does not rewrite. */
  lockTitle?: string;
  detail: ReactNode;
}

/**
 * The tree's visible rows. A folder starts open at the top level or on the way
 * to the open file; `overrides` holds what the user chose since, which wins
 * over that default (a plain flip would invert when opening a file makes its
 * folders "on the way" and collapse the folder just clicked in).
 */
function flatten(
  nodes: SkillFileNode[],
  depth: number,
  out: FileTreeRow[],
  ctx: { selected: string; locked: boolean; overrides: Map<string, boolean> },
): FileTreeRow[] {
  for (const node of sortSkillNodes(nodes)) {
    if (node.type === "dir") {
      const byDefault = depth < 1 || ctx.selected.startsWith(`${node.path}/`);
      const open = ctx.overrides.get(node.path) ?? byDefault;
      out.push({ key: node.path, name: node.name, kind: "folder", depth, open, title: node.path });
      if (open) flatten(node.children ?? [], depth + 1, out, ctx);
    } else {
      out.push({
        key: node.path,
        name: node.name,
        kind: "file",
        depth,
        title: node.path,
        selected: ctx.selected === node.path,
        locked: ctx.locked,
      });
    }
  }
  return out;
}

export function SkillFileSplit({
  name,
  tree,
  selected,
  onSelect,
  folderPath,
  lockTitle,
  detail,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const [overrides, setOverrides] = useState<Map<string, boolean>>(new Map());
  const reveal = folderPath ?? tree.data?.folder_abs_path ?? null;

  const rows = tree.data
    ? flatten(tree.data.children ?? [], 0, [], {
        selected,
        locked: Boolean(lockTitle),
        overrides,
      })
    : [];

  const side = (
    <FileTreePanel
      title={name}
      locked={lockTitle}
      action={
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-text-muted"
          aria-label={t("fileActions.reveal")}
          title={t("fileActions.reveal")}
          disabled={!reveal}
          onClick={() =>
            reveal && void fs.reveal(reveal).catch(() => toast.error(t("fileActions.revealFailed")))
          }
        >
          <FolderOpen aria-hidden />
        </Button>
      }
    >
      {tree.isPending ? (
        <div className="space-y-1.5 p-1" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : tree.error ? (
        <p className="p-1 text-xs text-danger">{translateApiError(t, tree.error)}</p>
      ) : (
        <FileTree
          rows={rows}
          label={t("skills.files.tree")}
          onActivate={(row) => {
            if (row.kind === "file") onSelect(row.key);
            else setOverrides((prev) => new Map(prev).set(row.key, !row.open));
          }}
        />
      )}
    </FileTreePanel>
  );

  return (
    <FileBrowserFrame
      side={side}
      main={detail}
      sideWidth={220}
      resizable={{
        storageKey: "skill-files",
        label: t("splitView.resizeList"),
        listMinWidth: SKILL_TREE_MIN,
        detailMinWidth: SKILL_FILE_MIN,
      }}
    />
  );
}
