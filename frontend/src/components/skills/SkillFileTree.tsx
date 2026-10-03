// frontend/src/components/skills/SkillFileTree.tsx
// File browser for a skill folder.
//
// `SkillFileTree` is the managed skill's Files tab (canvas 4.3.01): one card,
// the folder's files on the left — SKILL.md first, then folders, then files,
// no root row — and the open file on the right (SkillFileViewer). It opens on
// SKILL.md and keeps the open file in `?file=`, so a reload or a link lands on
// the same file; a file with unsaved edits wears a dot in the tree.
//
import { useState, type ReactNode } from "react";
import { useSearchParamsKeepingState as useSearchParams } from "@/lib/hooks/useSearchParamsKeepingState";
import { useTranslation } from "react-i18next";

import { useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { SkillFileViewer } from "@/components/skills/SkillFileViewer";
import { SkillTreeNode } from "@/components/skills/SkillTreeNodes";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useSkillFiles } from "@/lib/hooks/useSkills";
import { sortSkillNodes } from "@/lib/skills/tree";

/** The file a skill opens on: its SKILL.md, the one file every skill has. */
const DEFAULT_FILE = "SKILL.md";

/** The open file, kept in `?file=` (absent for the default). */
function useSelectedFile() {
  const [params, setParams] = useSearchParams();
  const selected = params.get("file") ?? DEFAULT_FILE;
  const select = (path: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (path === DEFAULT_FILE) next.delete("file");
        else next.set("file", path);
        return next;
      },
      { replace: true },
    );
  return { selected, select };
}

/** The Files card: the tree on the left, the open file on the right, both scrolling inside it. */
function SkillFileSplit({
  tree,
  selected,
  onSelect,
  dirtyPath = null,
  detail,
}: {
  tree: SkillFileTreeQuery;
  selected: string;
  onSelect: (path: string) => void;
  dirtyPath?: string | null;
  detail: ReactNode;
}) {
  const { t } = useTranslation();
  const fill = useFillToBottom();
  const list = (
    <nav aria-label={t("skills.files.tree")} className="min-h-0 flex-1 overflow-auto p-2">
      {tree.isPending ? (
        <div className="space-y-1.5 p-1" aria-busy="true">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : tree.error ? (
        <p className="p-1 text-xs text-danger">{translateApiError(t, tree.error)}</p>
      ) : tree.data ? (
        <ul className="space-y-0.5">
          {sortSkillNodes(tree.data.children ?? []).map((node) => (
            <SkillTreeNode
              key={node.path}
              node={node}
              depth={0}
              selectedPath={selected}
              onSelectFile={onSelect}
              dirtyPath={dirtyPath}
              flat
            />
          ))}
        </ul>
      ) : null}
    </nav>
  );

  return (
    // The card takes the window's height under the page header and tabs, and
    // both halves scroll inside it; the divider between them is draggable.
    <div
      ref={fill.ref}
      style={fill.style}
      className="flex min-h-0 overflow-hidden rounded-xl border border-border-subtle"
    >
      <SplitView
        storageKey="skill-files"
        label={t("splitView.resizeList")}
        defaultListWidth={216}
        className="min-h-0 flex-1"
        list={list}
        detail={detail}
      />
    </div>
  );
}

export function SkillFileTree({
  uid,
  owner,
  builtin = false,
}: {
  uid: string;
  owner: string;
  builtin?: boolean;
}) {
  const tree = useSkillFiles(uid);
  const { selected, select } = useSelectedFile();
  const [dirtyPath, setDirtyPath] = useState<string | null>(null);
  return (
    <SkillFileSplit
      tree={tree}
      selected={selected}
      onSelect={select}
      dirtyPath={dirtyPath}
      detail={
        <SkillFileViewer
          key={selected}
          uid={uid}
          owner={owner}
          path={selected}
          builtin={builtin}
          onDirtyChange={(dirty) => setDirtyPath(dirty ? selected : null)}
        />
      }
    />
  );
}

/** The tree query's state, whichever route it came from. */
interface SkillFileTreeQuery {
  isPending: boolean;
  error: unknown;
  data: SkillFileNode | undefined;
}
