// frontend/src/components/agents/AgentConfigFilesTab.tsx — spec agent-registry.
// The agent detail page's Config files tab: a resizable split of the curated
// config-file allowlist (ConfigFileTree — settings and instructions files side
// by side, grouped by where they live) and the selected file
// (ConfigEditorPane), or a directory entry's files (ConfigDirectoryPane).
// Credential and machine-state files are not on the allowlist, so never here.
//
// An unsaved draft is guarded three ways: picking another file asks first
// (the selection is parked in useConfigEditorState until confirmed), the page
// asks before switching tabs (`onDirtyChange`), and the browser asks before
// unload. The selected file is in the URL (`?file=`).
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { ConfigDirectoryPane } from "@/components/agents/ConfigDirectoryPane";
import { ConfigEditorPane } from "@/components/agents/ConfigEditorPane";
import { ConfigFileTree } from "@/components/agents/ConfigFileTree";
import { FILE_PANE_COLUMN, useFillToBottom } from "@/components/filePane";
import { SplitView } from "@/components/SplitView";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { baseName } from "@/lib/agents/configFiles";
import { agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useBeforeUnload } from "@/lib/hooks/useBeforeUnload";
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
  /** Reports whether an unsaved draft is on screen, so the page can guard
   *  tab switches that would unmount this tab. */
  onDirtyChange?: (dirty: boolean) => void;
}

export function AgentConfigFilesTab({ agent, onDirtyChange }: Props) {
  const { t } = useTranslation();
  const s = useConfigEditorState(agent.uid);
  const fill = useFillToBottom();
  const dirty = s.draft.dirty;
  const agentName = agentTypeLabel(agent.type);

  useBeforeUnload(dirty);
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

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
    <p className="px-2 text-sm text-danger">{translateApiError(t, s.files.error)}</p>
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
      <ConfirmDialog
        open={s.hasPendingSelection}
        onOpenChange={(open) => {
          if (!open) s.cancelPendingSelection();
        }}
        title={t("common.discardChanges.title")}
        description={t("common.discardChanges.body")}
        confirmLabel={t("common.discardChanges.confirm")}
        onConfirm={s.confirmPendingSelection}
      />
    </div>
  );
}
