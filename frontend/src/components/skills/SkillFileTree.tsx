// frontend/src/components/skills/SkillFileTree.tsx
// Two-pane read-only file browser for a skill's master folder (the Files tab):
// a recursive left tree (expand/collapse dirs, click a file to select it) and a
// right content pane. The content pane renders the file as a read-only <pre>;
// binary files show a placeholder and truncated files show a note. Mirrors the
// AgentConfigFilesEditor layout, minus editing.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight, FileText, Folder, FolderOpen } from "lucide-react";

import { translateApiError } from "@/lib/api/errors";
import type { SkillFileNode } from "@/lib/api/skills";
import { useSkillFileContent, useSkillFiles } from "@/lib/hooks/useSkills";
import { cn } from "@/lib/utils";

export function SkillFileTree({ name }: { name: string }) {
  const { t } = useTranslation();
  const tree = useSkillFiles(name);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const content = useSkillFileContent(name, selectedPath);

  return (
    <div className="grid gap-4 md:grid-cols-[18rem_1fr]">
      {/* Left: the recursive file tree. */}
      <div className="space-y-1">
        <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("skills.files.tree")}
        </p>
        {tree.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : tree.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, tree.error)}</p>
        ) : tree.data ? (
          <ul className="space-y-0.5">
            <TreeNode
              node={tree.data}
              depth={0}
              selectedPath={selectedPath}
              onSelectFile={setSelectedPath}
              isRoot
            />
          </ul>
        ) : null}
      </div>

      {/* Right: read-only content of the selected file. */}
      <div className="min-w-0">
        {selectedPath ? (
          <div className="space-y-2">
            <span className="block truncate font-mono text-xs text-muted-foreground">
              {selectedPath}
            </span>
            {content.isPending ? (
              <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
            ) : content.error ? (
              <p className="text-sm text-destructive" role="alert">
                {translateApiError(t, content.error)}
              </p>
            ) : content.data?.binary ? (
              <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
                {t("skills.files.binary", { size: content.data.size })}
              </div>
            ) : (
              <>
                <pre className="h-80 w-full overflow-auto rounded border bg-background p-2 font-mono text-xs text-foreground">
                  {content.data?.content ?? ""}
                </pre>
                {content.data?.truncated ? (
                  <p className="text-xs text-muted-foreground">{t("skills.files.truncated")}</p>
                ) : null}
              </>
            )}
          </div>
        ) : (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("skills.files.selectFile")}
          </div>
        )}
      </div>
    </div>
  );
}

function TreeNode({
  node,
  depth,
  selectedPath,
  onSelectFile,
  isRoot = false,
}: {
  node: SkillFileNode;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
  isRoot?: boolean;
}) {
  // Root + its immediate children start expanded so the tree is useful at a glance.
  const [expanded, setExpanded] = useState(depth < 2);
  const indent = { paddingLeft: `${depth * 0.75 + 0.25}rem` };

  if (node.type === "dir") {
    return (
      <li>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          style={indent}
          aria-expanded={expanded}
          className="flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors hover:bg-secondary hover:text-foreground"
        >
          {expanded ? (
            <ChevronDown className="size-3.5 shrink-0 opacity-70" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0 opacity-70" />
          )}
          {expanded ? (
            <FolderOpen className="size-4 shrink-0 opacity-70" />
          ) : (
            <Folder className="size-4 shrink-0 opacity-70" />
          )}
          <span className="truncate">{isRoot ? node.name || "/" : node.name}</span>
        </button>
        {expanded && node.children ? (
          <ul className="space-y-0.5">
            {node.children.map((child) => (
              <TreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelectFile={onSelectFile}
              />
            ))}
          </ul>
        ) : null}
      </li>
    );
  }

  return (
    <li>
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        style={indent}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-md py-1.5 pr-2 text-left text-sm transition-colors",
          selectedPath === node.path
            ? "bg-primary/10 text-primary"
            : "hover:bg-secondary hover:text-foreground",
        )}
      >
        <span className="size-3.5 shrink-0" />
        <FileText className="size-4 shrink-0 opacity-70" />
        <span className="truncate">{node.name}</span>
      </button>
    </li>
  );
}
