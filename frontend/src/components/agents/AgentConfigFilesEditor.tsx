// frontend/src/components/agents/AgentConfigFilesEditor.tsx — spec 004.
// Two-pane config editor for one agent: a left "tree" of the curated, editable
// config files (the allowlist — credential and machine-state files are
// deliberately excluded), and a right pane that shows the selected file in an
// editable textarea with a Save control. Saving writes atomically and keeps a
// `.bak` of the prior content; malformed JSON/TOML is rejected server-side and
// the on-disk file is left unchanged. A dependency-free find/replace bar
// (toggled by a button) operates on the editable content.
//
// Directory-backed config keys (kind === "directory", e.g. a memory dir)
// render as expandable nodes whose children come from the list response; a
// child opens in the same right pane, can be created (markdown only) and
// deleted. Saves pass the content query's `expected_fingerprint` so a file
// changed on disk since it was read is rejected with 409 CONFIG_FILE_STALE
// and surfaced as a reload banner instead of silently clobbered.
//
// Composition only: state + data plumbing live in useConfigEditorState; the
// presentation lives in ConfigFileTree (left pane), ConfigEditorPane (right
// pane), and ConfigEditorDialogs (new-file + delete-child modals).
import { useTranslation } from "react-i18next";

import {
  DeleteChildDialog,
  NewChildFileDialog,
} from "@/components/agents/ConfigEditorDialogs";
import { ConfigEditorPane } from "@/components/agents/ConfigEditorPane";
import { ConfigFileTree } from "@/components/agents/ConfigFileTree";
import { translateApiError } from "@/lib/api/errors";
import { useConfigEditorState } from "@/lib/hooks/useConfigEditorState";

// Keys that have a human description under `agents.config.desc.<key>`. Listing
// them explicitly keeps an unknown/new key from rendering a raw i18n string.
// The copy is shown in the right pane (next to the content), not the left tree.
const DESCRIBED_KEYS = new Set([
  "settings",
  "settings_local",
  "global",
  "instructions",
  "subagents",
  "config",
  "hooks",
]);

export function AgentConfigFilesEditor({ name }: { name: string }) {
  const { t } = useTranslation();
  const s = useConfigEditorState(name);

  // One-line "what is this file for" description for the selected key, only for
  // keys we have copy for; unknown keys render nothing rather than a raw key.
  const description =
    s.selectedKey && DESCRIBED_KEYS.has(s.selectedKey)
      ? t(`agents.config.desc.${s.selectedKey}`)
      : null;

  return (
    <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
      {/* Left: the config-file tree (allowlisted files + directory nodes). */}
      <div className="space-y-1">
        <p className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t("agents.config.files")}
        </p>
        {s.files.isPending ? (
          <p className="px-1 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : s.files.error ? (
          <p className="px-1 text-sm text-destructive">{translateApiError(t, s.files.error)}</p>
        ) : s.allFiles.length === 0 ? (
          <p className="px-1 text-sm text-muted-foreground">{t("agents.config.none")}</p>
        ) : (
          <ConfigFileTree
            files={s.allFiles}
            selectedKey={s.selectedKey}
            selectedChild={s.selectedChild}
            expandedDirs={s.expandedDirs}
            onSelectFile={s.selectFile}
            onSelectDirectory={s.selectDirectory}
            onSelectChild={s.selectChild}
            onNewFile={s.openNewFileDialog}
          />
        )}
      </div>

      {/* Right: editable view of the selected file (or directory hint). */}
      <div className="min-w-0">
        {s.selectedKey && s.isDirSelected ? (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("agents.config.directoryHint")}
          </div>
        ) : s.selectedKey ? (
          <ConfigEditorPane
            pathLabel={
              s.selectedChild
                ? `${s.selectedInfo?.path ?? s.selectedKey}/${s.selectedChild}`
                : (s.selectedInfo?.path ?? s.selectedKey)
            }
            description={description}
            formatLabel={s.activeContent?.format ?? s.selectedInfo?.format}
            editorKey={s.selectedChild ?? s.selectedKey}
            draft={s.draft}
            loading={s.activeQuery.isPending}
            onDraftChange={s.updateDraft}
            textareaRef={s.textareaRef}
            showFind={s.showFind}
            onToggleFind={() => s.setShowFind((v) => !v)}
            onDeleteChild={
              s.selectedChild
                ? () => {
                    if (s.selectedKey && s.selectedChild) {
                      s.setDeleteTarget({ key: s.selectedKey, relpath: s.selectedChild });
                    }
                  }
                : null
            }
            stale={s.stale}
            onReloadStale={s.onReloadStale}
            memoryBlock={s.memoryBlock}
            saveError={s.activeSave.error}
            saved={s.saved}
            savePending={s.activeSave.isPending}
            saveDisabled={!s.dirty || s.activeSave.isPending || s.activeQuery.isPending}
            onSave={s.onSave}
          />
        ) : (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("agents.config.selectFile")}
          </div>
        )}
      </div>

      <NewChildFileDialog
        dirKey={s.newFileDir}
        dirPath={s.allFiles.find((f) => f.key === s.newFileDir)?.path ?? null}
        name={s.newFileName}
        invalid={s.newFileInvalid}
        error={s.createChild.error}
        pending={s.createChild.isPending}
        onNameChange={s.setNewFileNameValid}
        onSubmit={s.submitNewFile}
        onClose={() => s.setNewFileDir(null)}
      />

      <DeleteChildDialog
        target={s.deleteTarget}
        pending={s.deleteChild.isPending}
        onConfirm={s.confirmDeleteChild}
        onClose={() => s.setDeleteTarget(null)}
      />
    </div>
  );
}
