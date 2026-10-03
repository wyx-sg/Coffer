// frontend/src/components/agents/UnmanagedSkillFiles.tsx — spec skill-manager
// "Preview an unmanaged skill read-only".
// The Files tab of an unmanaged skill's detail page (board 2.1.58): ONE bordered
// surface — the folder as the shared file tree (its name in the header strip
// with a lock and a Reveal icon) beside a read-only viewer of the selected file
// (viewer toolbar, Preview / Source for Markdown, front matter as a key / value
// grid). SKILL.md opens first.
//
// The viewer only reads. Coffer does not own these bytes until the folder is
// adopted, so there is no draft, no fingerprint and no save — Open in editor is
// the honest way to change something another tool put there.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { LoadError } from "@/components/LoadError";
import { FileBrowserFrame } from "@/components/files/FileBrowserFrame";
import { FileTree, FileTreePanel, type FileTreeRow } from "@/components/files/FileTree";
import { ReadOnlyFile } from "@/components/files/ReadOnlyFile";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { SkillFileNode } from "@/lib/api/skills";
import { useFsActions } from "@/lib/fsActions";
import {
  useUnmanagedSkillFileContent,
  useUnmanagedSkillFiles,
} from "@/lib/hooks/useUnmanagedSkill";

interface Props {
  agentUid: string;
  location: string;
  name: string;
}

/** The relative path of the first file named SKILL.md at the folder's top, if any. */
function skillMd(root: SkillFileNode | undefined): string | null {
  const hit = root?.children.find((c) => c.type === "file" && c.name === "SKILL.md");
  return hit ? hit.path || hit.name : null;
}

export function UnmanagedSkillFiles({ agentUid, location, name }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const tree = useUnmanagedSkillFiles(agentUid, location, name);
  const [picked, setPicked] = useState<string | null>(null);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const root = tree.data;
  const selected = picked ?? skillMd(root);
  const content = useUnmanagedSkillFileContent(agentUid, location, name, selected);

  const rows: FileTreeRow[] = [];
  const walk = (nodes: SkillFileNode[], depth: number) => {
    for (const node of nodes) {
      const path = node.path || node.name;
      if (node.type === "dir") {
        const open = !closed.has(path);
        rows.push({ key: path, name: node.name, kind: "folder", depth, open });
        if (open) walk(node.children, depth + 1);
      } else {
        rows.push({
          key: path,
          name: node.name,
          kind: "file",
          depth,
          selected: selected === path,
          title: path,
        });
      }
    }
  };
  if (root) walk(root.children, 0);

  const side = (
    <FileTreePanel
      title={<span className="font-mono text-xs">{name}</span>}
      locked
      action={
        root ? (
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={t("fileActions.reveal")}
            title={t("fileActions.reveal")}
            onClick={() =>
              void reveal(root.abs_path).catch(() => toast.error(t("fileActions.revealFailed")))
            }
          >
            <FolderOpen aria-hidden />
          </Button>
        ) : null
      }
    >
      {tree.isPending ? (
        <p className="px-2 text-sm text-text-muted">{t("common.loading")}</p>
      ) : tree.error ? (
        <LoadError className="px-1" error={tree.error} onRetry={() => void tree.refetch()} />
      ) : (
        <FileTree
          rows={rows}
          label={t("agents.skillsTab.unmanagedDetail.filesLabel")}
          onActivate={(row) => {
            if (row.kind === "file") setPicked(row.key);
            else
              setClosed((prev) => {
                const next = new Set(prev);
                if (next.has(row.key)) next.delete(row.key);
                else next.add(row.key);
                return next;
              });
          }}
        />
      )}
    </FileTreePanel>
  );

  const main = selected ? (
    <ReadOnlyFile
      key={selected}
      path={selected}
      displayPath={abbreviateHomePath(
        content.data?.abs_path ?? `${root?.abs_path ?? name}/${selected}`,
      )}
      query={content}
    />
  ) : (
    <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-muted">
      {t("agents.memoryStore.selectFile")}
    </div>
  );

  return <FileBrowserFrame side={side} main={main} />;
}
