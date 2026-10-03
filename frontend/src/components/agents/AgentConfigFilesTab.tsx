// frontend/src/components/agents/AgentConfigFilesTab.tsx — spec agent-registry.
// The agent detail page's Config files tab: a resizable split of the curated
// config-file allowlist (ConfigFileTree — settings and instructions files side
// by side, grouped by where they live) and the selected file
// (ConfigEditorPane), or a directory entry's files (ConfigDirectoryPane).
// Secret and machine-state files are not on the allowlist, so never here.
//
// An unsaved draft is guarded by the shell, not here: the file picker, the tab
// strip and every other way out are location changes, and the shell's guard
// dialog asks first (useUnsavedGuard, registered by the draft itself). The
// selected file is in the URL (`?file=`).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { LoadError } from "@/components/LoadError";
import { ConfigDirectoryPane } from "@/components/agents/ConfigDirectoryPane";
import { ConfigEditorPane } from "@/components/agents/ConfigEditorPane";
import { ConfigFileTree } from "@/components/agents/ConfigFileTree";
import { NewConfigFileDialog } from "@/components/agents/NewConfigFileDialog";
import { FILE_PANE_COLUMN, useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { baseName } from "@/lib/agents/configFiles";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { useCreateConfigChild, useDeleteConfigChild } from "@/lib/hooks/useConfigDirFiles";
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

const QUIET =
  "flex min-h-0 flex-1 items-center justify-center rounded-md border border-dashed text-sm text-text-muted";

interface Props {
  agent: AgentOut;
}

export function AgentConfigFilesTab({ agent }: Props) {
  const { t } = useTranslation();
  const agentName = agentTypeLabel(agent.type);
  const s = useConfigEditorState(agent.uid, agentName);
  const fill = useFillToBottom();
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
    <div ref={fill.ref} style={fill.style} className="flex min-h-0">
      <SplitView
        storageKey="agent-config"
        label={t("splitView.resizeList")}
        className="min-h-0 flex-1"
        listClassName={FILE_PANE_COLUMN}
        detailClassName="pl-4"
        list={list}
        detail={detail}
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
    </div>
  );
}
