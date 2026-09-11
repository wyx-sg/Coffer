// frontend/src/components/agents/AgentConfigFilesEditor.tsx — spec agent-registry.
// Two-pane config editor for one agent: a left "tree" of the curated config
// files (the allowlist — credential and machine-state files are deliberately
// excluded), and a right pane showing the selected file's on-disk content,
// editable behind an explicit Edit. The right pane also carries a FileActions
// bar (open-in-editor / reveal) for the edits that want a real editor, and the
// managed-block notice (FR-037) warns that the block may be rewritten.
//
// Directory-backed config keys (kind === "directory", e.g. a memory dir)
// render as expandable nodes whose children come from the list response; a
// child opens in the same right pane.
//
// Composition only: state + data plumbing live in useConfigEditorState; the
// presentation lives in ConfigFileTree (left pane) and ConfigEditorPane (right
// pane).
import { useTranslation } from "react-i18next";

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
  "soul",
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

  // Absolute path for the external-editor action. The content response is the
  // most precise source (it resolves the actual file/child on disk); fall back
  // to the list metadata for the selected top-level key.
  const filePath = s.activeContent?.path ?? (s.selectedChild ? undefined : s.selectedInfo?.path);

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
          />
        )}
      </div>

      {/* Right: the selected file (or directory hint). */}
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
            filePath={filePath}
            description={description}
            formatLabel={s.activeContent?.format ?? s.selectedInfo?.format}
            editorKey={s.selectedChild ?? s.selectedKey}
            content={s.activeContent?.content ?? ""}
            loading={s.activeQuery.isPending}
            memoryBlock={s.memoryBlock}
            draft={s.draft}
            readOnlyMissing={s.readOnlyMissing}
          />
        ) : (
          <div className="flex h-80 items-center justify-center rounded border border-dashed text-sm text-muted-foreground">
            {t("agents.config.selectFile")}
          </div>
        )}
      </div>
    </div>
  );
}
