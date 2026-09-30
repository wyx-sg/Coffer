// frontend/src/components/skills/SkillFileTree.tsx
// File browsers for a skill folder.
//
// `SkillFileTree` is the managed skill's Files tab (canvas 4.3.01): one card,
// the folder's files on the left — SKILL.md first, then folders, then files,
// no root row — and the open file on the right (SkillFileViewer). It opens on
// SKILL.md and keeps the open file in `?file=`, so a reload or a link lands on
// the same file; a file with unsaved edits wears a dot in the tree.
//
// `SkillFileBrowser` is the older two-column shape the unmanaged preview
// (UnmanagedSkillFiles) binds to its read-only routes.
import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  FILE_PANE_COLUMN,
  FILE_PANE_GRID,
  FILE_PANE_SCROLL,
  useFillToBottom,
} from "@/components/filePane";
import { SkillFileViewer } from "@/components/skills/SkillFileViewer";
import { SkillTreeNode } from "@/components/skills/SkillTreeNodes";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useSkillFiles } from "@/lib/hooks/useSkills";
import { sortSkillNodes } from "@/lib/skills/tree";
import { cn } from "@/lib/utils";

/** The file a skill opens on: its SKILL.md, the one file every skill has. */
const DEFAULT_FILE = "SKILL.md";

export function SkillFileTree({ uid, builtin = false }: { uid: string; builtin?: boolean }) {
  const { t } = useTranslation();
  const tree = useSkillFiles(uid);
  const [params, setParams] = useSearchParams();
  const [dirtyPath, setDirtyPath] = useState<string | null>(null);
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

  return (
    // The card takes the window's height under the page header and tabs, and
    // both halves scroll inside it; the reading pane scrolls past banners.
    <div className="grid h-[calc(100vh-15rem)] min-h-80 grid-rows-[minmax(0,2fr)_minmax(0,3fr)] overflow-hidden rounded-xl border border-border-subtle md:grid-cols-[13.5rem_minmax(0,1fr)] md:grid-rows-[minmax(0,1fr)]">
      <nav
        aria-label={t("skills.files.tree")}
        className="min-h-0 overflow-auto border-b border-border-subtle p-2 md:border-b-0 md:border-r"
      >
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
                onSelectFile={select}
                dirtyPath={dirtyPath}
                flat
              />
            ))}
          </ul>
        ) : null}
      </nav>
      <div className="flex min-h-0 min-w-0 flex-col">
        <SkillFileViewer
          key={selected}
          uid={uid}
          path={selected}
          builtin={builtin}
          onDirtyChange={(dirty) => setDirtyPath(dirty ? selected : null)}
        />
      </div>
    </div>
  );
}

/** The tree query's state, whichever route it came from. */
export interface SkillFileTreeQuery {
  isPending: boolean;
  error: unknown;
  data: SkillFileNode | undefined;
}

export function SkillFileBrowser({
  tree,
  renderFile,
}: {
  tree: SkillFileTreeQuery;
  renderFile: (path: string) => ReactNode;
}) {
  const { t } = useTranslation();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const fill = useFillToBottom();

  return (
    <div
      ref={fill.ref}
      style={fill.style}
      className={cn(FILE_PANE_GRID, "md:grid-cols-[18rem_minmax(0,1fr)]")}
    >
      <div className={FILE_PANE_COLUMN}>
        <p className="shrink-0 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("skills.files.tree")}
        </p>
        {tree.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : tree.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, tree.error)}</p>
        ) : tree.data ? (
          <ul className={cn("space-y-0.5", FILE_PANE_SCROLL)}>
            <SkillTreeNode
              node={tree.data}
              depth={0}
              selectedPath={selectedPath}
              onSelectFile={setSelectedPath}
              isRoot
            />
          </ul>
        ) : null}
      </div>
      <div className={FILE_PANE_COLUMN}>
        {selectedPath ? (
          renderFile(selectedPath)
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
            {t("skills.files.selectFile")}
          </div>
        )}
      </div>
    </div>
  );
}
