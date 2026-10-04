// frontend/src/components/agents/AgentConfigFilesTab.tsx — spec agent-registry.
// The agent detail page's Config files tab (boards 2.1.40–2.1.48): ONE bordered
// surface — the curated config-file allowlist as a tree on the left (settings
// and instructions files side by side, grouped by where they live;
// ConfigFileTree) and the selected file on the right (ConfigEditorPane), or a
// directory entry's files (ConfigDirectoryPane). It stays a document editor:
// reading first, an explicit Edit · Revert · Save, an unsaved guard.
// Secret and machine-state files are not on the allowlist, so never here.
//
// An unsaved draft is guarded by the shell, not here: the file picker, the tab
// strip and every other way out are location changes, and the shell's guard
// dialog asks first (useUnsavedGuard, registered by the draft itself). The
// selected file is in the URL (`?file=`).
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen } from "lucide-react";

import { LoadError } from "@/components/LoadError";
import { ConfigDirectoryPane } from "@/components/agents/ConfigDirectoryPane";
import { ConfigEditorPane } from "@/components/agents/ConfigEditorPane";
import { ConfigFileTree } from "@/components/agents/ConfigFileTree";
import { NewConfigFileDialog } from "@/components/agents/NewConfigFileDialog";
import { FileBrowserFrame } from "@/components/files/FileBrowserFrame";
import { FileTreePanel } from "@/components/files/FileTree";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useFsActions } from "@/lib/fsActions";
import { useCreateConfigChild, useDeleteConfigChild } from "@/lib/hooks/useConfigDirFiles";
import { useToast } from "@/components/ui/toast";
import { useConfigEditorState } from "@/lib/hooks/useConfigEditorState";

// Keys with a description under `agents.config.desc.<key>`. Listing them keeps
// an unknown/new key from rendering a raw i18n string.
const DESCRIBED_KEYS = new Set([
  "settings",
  "settings_local",
  "global",
  "instructions",
  "subagents",
  "config",
  "hooks",
]);

const QUIET = "flex min-h-0 flex-1 items-center justify-center text-sm text-text-muted";

interface Props {
  agent: AgentOut;
}

export function AgentConfigFilesTab({ agent }: Props) {
  const { t } = useTranslation();
  const agentName = agentTypeLabel(agent.type);
  const s = useConfigEditorState(agent.uid, agentName);
  const { reveal } = useFsActions();
  const { toast } = useToast();
  const createChild = useCreateConfigChild(agent.uid);
  const deleteChild = useDeleteConfigChild(agent.uid);
  const [newFileOpen, setNewFileOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{
    key: string;
    relpath: string;
    path: string;
  } | null>(null);

  const description =
    s.selectedKey && DESCRIBED_KEYS.has(s.selectedKey) && !s.selectedChild
      ? t(`agents.config.desc.${s.selectedKey}`, { agent: agentName })
      : null;
  // The content response resolves the actual file on disk; the listing covers
  // a top-level file before its content has loaded.
  const filePath = s.activeContent?.path ?? (s.selectedChild ? undefined : s.selectedInfo?.path);

  const list = s.files.isPending ? (
    <p className="px-2 text-sm text-text-muted">{t("common.loading")}</p>
  ) : s.files.error ? (
    <LoadError className="px-2" error={s.files.error} onRetry={() => void s.files.refetch()} />
  ) : s.allFiles.length === 0 ? (
    <p className="px-2 text-sm text-text-muted">{t("agents.config.none")}</p>
  ) : (
    <ConfigFileTree
      files={s.allFiles}
      dirty={s.draft.dirty}
      selectedKey={s.selectedKey}
      selectedChild={s.selectedChild}
      collapsed={s.collapsed}
      onSelectFile={s.selectFile}
      onSelectDirectory={s.selectDirectory}
      onSelectChild={s.selectChild}
    />
  );

  const detail =
    s.selectedInfo && s.isDirSelected ? (
      <ConfigDirectoryPane
        agentUid={agent.uid}
        entry={s.selectedInfo}
        description={description}
        onSelectChild={(relpath) => s.selectChild(s.selectedInfo?.key ?? "", relpath)}
        onNewFile={() => setNewFileOpen(true)}
        onDeleteChild={(relpath) => {
          const entry = s.selectedInfo;
          if (!entry) return;
          deleteChild.reset();
          setDeleteTarget({ key: entry.key, relpath, path: `${entry.path}/${relpath}` });
        }}
      />
    ) : s.selectedInfo ? (
      <ConfigEditorPane
        key={`${s.selectedKey}/${s.selectedChild ?? ""}`}
        name={s.selectedChild ?? baseName(s.selectedInfo.path)}
        filePath={filePath}
        description={description}
        format={s.activeContent?.format ?? s.selectedInfo.format}
        content={s.activeContent?.content ?? ""}
        loading={s.activeQuery.isPending}
        draft={s.draft}
        missing={s.missing}
        agentName={agentName}
      />
    ) : (
      <div className={QUIET}>{t("agents.config.selectFile")}</div>
    );

  return (
    <>
      <FileBrowserFrame
        side={
          <FileTreePanel
            title={t("agents.configTab.title", { agent: agentName })}
            action={
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t("fileActions.reveal")}
                title={t("fileActions.reveal")}
                onClick={() =>
                  void reveal(agent.config_dir).catch(() =>
                    toast.error(t("fileActions.revealFailed")),
                  )
                }
              >
                <FolderOpen aria-hidden />
              </Button>
            }
          >
            {list}
          </FileTreePanel>
        }
        main={detail}
      />
      {s.selectedInfo && s.isDirSelected ? (
        <NewConfigFileDialog
          open={newFileOpen}
          onOpenChange={setNewFileOpen}
          entry={s.selectedInfo}
          onCreate={async (relpath, content) => {
            const key = s.selectedInfo?.key ?? "";
            await createChild.mutateAsync({ key, relpath, content });
            s.selectChild(key, relpath);
          }}
        />
      ) : null}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t("agents.configTab.deleteTitle", { name: deleteTarget?.relpath ?? "" })}
        description={t("agents.configTab.deleteBody", {
          path: deleteTarget ? abbreviateHomePath(deleteTarget.path) : "",
          agent: agentName,
        })}
        confirmLabel={t("common.delete")}
        pending={deleteChild.isPending}
        error={deleteChild.error}
        onConfirm={() =>
          deleteTarget
            ? deleteChild.mutateAsync({ key: deleteTarget.key, relpath: deleteTarget.relpath })
            : undefined
        }
      />
    </>
  );
}
