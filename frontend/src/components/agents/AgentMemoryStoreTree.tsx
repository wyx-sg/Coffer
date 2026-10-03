// frontend/src/components/agents/AgentMemoryStoreTree.tsx — spec agent-registry
// "Read one native memory store's files read-only".
//
// ONE bordered surface for ONE of the agent's own native memory stores
// (boards 2.1.51, 2.1.61): the store directory as the shared read-only file
// tree (header strip "Files" with a lock, a lock at each row, a row menu with
// Copy path and Reveal in Finder) beside the selected file's viewer
// (AgentMemoryStoreFileViewer). The index file (MEMORY.md) opens first when
// the store has one.
//
// The store IS that directory — Claude Code writes one Markdown file per fact
// into it, Codex keeps one global document — so showing the folder is the most
// honest surface available: what the reader sees here is exactly what the agent
// will be handed, with no interpretation layered over it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { LoadError } from "@/components/LoadError";
import { AgentMemoryStoreFileViewer } from "@/components/agents/AgentMemoryStoreFileViewer";
import { FileBrowserFrame } from "@/components/files/FileBrowserFrame";
import { FileTree, FileTreePanel, type FileTreeRow } from "@/components/files/FileTree";
import { ActionMenu } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { NativeMemoryFileNode } from "@/lib/api/agentNativeMemory";
import { useFsActions } from "@/lib/fsActions";
import { useNativeMemoryFiles } from "@/lib/hooks/useAgentNativeMemory";

function RowMenu({ name, absPath }: { name: string; absPath: string }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  return (
    <ActionMenu
      label={t("agents.memoryStore.moreFor", { name })}
      actions={[
        {
          key: "copy",
          label: t("agents.memoryStore.copyPath"),
          onSelect: () =>
            void navigator.clipboard
              .writeText(absPath)
              .then(() => toast.success(t("common.copied")))
              .catch(() => toast.error(t("agents.memoryStore.copyFailed"))),
        },
        {
          key: "reveal",
          label: t("fileActions.reveal"),
          onSelect: () =>
            void reveal(absPath).catch(() => toast.error(t("fileActions.revealFailed"))),
        },
      ]}
    />
  );
}

export function AgentMemoryStoreTree({ agentUid, dir }: { agentUid: string; dir: string }) {
  const { t } = useTranslation();
  const tree = useNativeMemoryFiles(agentUid, dir);
  const [picked, setPicked] = useState<string | null>(null);
  // Folders the reader flipped from their default (the first level starts open).
  const [flipped, setFlipped] = useState<Set<string>>(new Set());
  const root = tree.data?.root;
  // Until the reader picks one, the store's index file is the one to read.
  const index = root?.children.find((c) => c.type === "file" && c.name === "MEMORY.md");
  const selectedPath = picked ?? index?.path ?? null;

  const rows: FileTreeRow[] = [];
  const walk = (nodes: NativeMemoryFileNode[], depth: number) => {
    for (const node of nodes) {
      if (node.type === "dir") {
        const open = depth < 1 !== flipped.has(node.path);
        rows.push({
          key: node.path,
          name: node.name,
          kind: "folder",
          depth,
          open,
          leaf: node.children.length === 0,
        });
        if (open) walk(node.children, depth + 1);
      } else {
        rows.push({
          key: node.path,
          name: node.name,
          kind: "file",
          depth,
          selected: selectedPath === node.path,
          locked: true,
          title: node.path,
          menu: <RowMenu name={node.name} absPath={`${dir.replace(/\/+$/, "")}/${node.path}`} />,
        });
      }
    }
  };
  if (root) walk(root.children, 0);

  const side = (
    <FileTreePanel title={t("agents.memoryStore.tree")} locked>
      {tree.isPending ? (
        <p className="px-2 text-sm text-text-muted">{t("common.loading")}</p>
      ) : tree.error ? (
        <LoadError className="px-1" error={tree.error} onRetry={() => void tree.refetch()} />
      ) : (
        <FileTree
          rows={rows}
          label={t("agents.memoryStore.tree")}
          onActivate={(row) => {
            if (row.kind === "file") setPicked(row.key);
            else
              setFlipped((prev) => {
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

  const main = selectedPath ? (
    <AgentMemoryStoreFileViewer
      key={selectedPath}
      agentUid={agentUid}
      dir={dir}
      path={selectedPath}
    />
  ) : (
    <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-muted">
      {t("agents.memoryStore.selectFile")}
    </div>
  );

  return <FileBrowserFrame side={side} main={main} />;
}
