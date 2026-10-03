// frontend/src/components/skills/SkillFileSplit.tsx
// The Files card every skill folder is browsed in (canvas 4.3.01, 4.3.12,
// Foundations 0.6.04): one bordered card, the folder's tree on the left under a
// 36px header — the skill's name, a lock when the folder is read-only, and
// Reveal in Finder — and the open file on the right. SKILL.md opens first and
// the open file is kept in `?file=`, so a reload or a link lands on the same
// file. The managed skill (SkillFileTree) and the read-only folders
// (SkillReadOnlyFiles — an unmanaged skill, a folder not in the library) are
// this same card; only the file pane differs.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, Lock } from "lucide-react";

import { useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { SkillTreeNode } from "@/components/skills/SkillTreeNodes";
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
  dirtyPath?: string | null;
  /** The folder's absolute path, for Reveal in Finder; falls back to the tree's own. */
  folderPath?: string | null;
  /** Why the folder is read-only ("Written by Coffer — read-only"); absent when it can be edited. */
  lockTitle?: string;
  detail: ReactNode;
}

export function SkillFileSplit({
  name,
  tree,
  selected,
  onSelect,
  dirtyPath = null,
  folderPath,
  lockTitle,
  detail,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const fs = useFsActions();
  const fill = useFillToBottom();
  const reveal = folderPath ?? tree.data?.folder_abs_path ?? null;

  const list = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-9 shrink-0 items-center gap-1.5 border-b border-border-subtle pl-3 pr-2">
        <span className="min-w-0 truncate text-sm font-semibold text-text">{name}</span>
        {lockTitle ? (
          <span title={lockTitle} className="inline-flex text-text-subtle">
            <Lock className="size-[13px]" aria-label={lockTitle} role="img" />
          </span>
        ) : null}
        <span className="ml-auto inline-flex shrink-0 gap-0.5">
          <Button
            variant="ghost"
            size="icon-sm"
            className="text-text-muted"
            aria-label={t("fileActions.reveal")}
            title={t("fileActions.reveal")}
            disabled={!reveal}
            onClick={() =>
              reveal &&
              void fs.reveal(reveal).catch(() => toast.error(t("fileActions.revealFailed")))
            }
          >
            <FolderOpen aria-hidden />
          </Button>
        </span>
      </div>
      <nav aria-label={t("skills.files.tree")} className="min-h-0 flex-1 overflow-auto p-1">
        {tree.isPending ? (
          <div className="space-y-1.5 p-1" aria-busy="true">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        ) : tree.error ? (
          <p className="p-1 text-xs text-danger">{translateApiError(t, tree.error)}</p>
        ) : tree.data ? (
          <ul className="flex flex-col gap-px">
            {sortSkillNodes(tree.data.children ?? []).map((node) => (
              <SkillTreeNode
                key={node.path}
                node={node}
                depth={0}
                selectedPath={selected}
                onSelectFile={onSelect}
                dirtyPath={dirtyPath}
                readOnly={Boolean(lockTitle)}
              />
            ))}
          </ul>
        ) : null}
      </nav>
    </div>
  );

  return (
    // The card takes the window's height under the page header and tabs, and
    // both halves scroll inside it; the divider between them is draggable. In a
    // narrow window the tree shrinks to its minimum, the file keeps its own,
    // and below that the card scrolls sideways rather than squeezing the file.
    <div
      ref={fill.ref}
      style={fill.style}
      className="flex min-h-0 overflow-x-auto overflow-y-hidden rounded-xl border border-border-subtle"
    >
      <SplitView
        storageKey="skill-files"
        label={t("splitView.resizeList")}
        defaultListWidth={220}
        className="min-h-0 min-w-[504px] flex-1"
        listMinWidth={SKILL_TREE_MIN}
        detailMinWidth={SKILL_FILE_MIN}
        list={list}
        detail={detail}
      />
    </div>
  );
}
