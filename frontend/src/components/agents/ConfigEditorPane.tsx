// frontend/src/components/agents/ConfigEditorPane.tsx — spec agent-registry.
// Right pane of the agent's Config files tab: the file's name with its state
// (Read-only, Unsaved change, Not created) and what it is for, the
// open-in-editor / reveal actions with Edit (or Revert and Save), the content,
// and a footer naming the format, how a save behaves and the absolute path.
//
// Reading is the default: these are the agent's real configuration, so a pane
// opened to look cannot be changed by a stray keystroke. A JSON draft is
// checked as it is typed — the line and column where it stops parsing are
// shown and Save waits until it parses (the daemon refuses malformed JSON
// anyway). A save refused because the file changed on disk keeps the draft
// (ConfigStalePanel); a file the agent has not created yet shows the panel
// that creates it (ConfigMissingPanel). All state is the parent's draft.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfigMissingPanel, ConfigStalePanel } from "@/components/agents/ConfigEditorNotices";
import { FileActions } from "@/components/FileActions";
import { FILE_PANE_BODY } from "@/components/filePane";
import { CodeView } from "@/components/preview/CodeView";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { checkJson } from "@/lib/agents/configFiles";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";
import { cn } from "@/lib/utils";

export interface ConfigEditorPaneProps {
  /** The file's own name (`settings.json`, or a directory file's relpath). */
  name: string;
  /** Absolute on-disk path (external-editor actions and the footer). */
  filePath?: string;
  /** One-line "what is this file for" copy. */
  description?: string | null;
  format: ConfigFileInfo["format"] | undefined;
  /** The file's current on-disk content (read-only). */
  content: string;
  /** True while the content query is loading (preview renders empty). */
  loading: boolean;
  /** Draft/save state for this file, owned by the parent's editor state. */
  draft: ReturnType<typeof useFileDraft>;
  /** The file is not on disk yet; saving creates it. */
  missing: boolean;
  /** The agent's product name, for the not-created copy. */
  agentName: string;
}

const FORMAT_LABEL: Record<ConfigFileInfo["format"], string> = {
  json: "JSON",
  toml: "TOML",
  markdown: "Markdown",
};

export function ConfigEditorPane(props: ConfigEditorPaneProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { draft } = props;
  const [confirmRevert, setConfirmRevert] = useState(false);

  // `save` fires a mutation the draft owns; success is a save that settles
  // without an error.
  const wasSaving = useRef(false);
  useEffect(() => {
    if (wasSaving.current && !draft.saving && !draft.error) toast.success(t("common.saved"));
    wasSaving.current = draft.saving;
  }, [draft.saving, draft.error, toast, t]);

  const json = props.format === "json" && draft.editing ? checkJson(draft.value) : null;
  const invalid = json !== null && !json.ok;
  const showMissing = props.missing && !draft.editing;

  const marker = showMissing
    ? t("agents.configTab.markerMissing")
    : draft.editing
      ? draft.dirty
        ? t("agents.configTab.markerDirty")
        : t("agents.configTab.markerEditing")
      : t("agents.configTab.markerReadOnly");

  const create = () => {
    draft.startEditing();
    if (props.format === "json") draft.setDraft("{}\n");
  };
  const revert = () => (draft.dirty ? setConfirmRevert(true) : draft.cancel());

  const formatLine = json
    ? json.ok
      ? t("agents.configTab.validJson")
      : t("agents.configTab.invalidJson", { line: json.line, column: json.column })
    : props.format
      ? FORMAT_LABEL[props.format]
      : null;
  const note = showMissing
    ? t("agents.configTab.noteMissing")
    : draft.editing
      ? t("agents.configTab.noteEditing")
      : t("agents.configTab.noteViewing");

  return (
    <div className={FILE_PANE_BODY}>
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-baseline gap-2">
            <span className="break-all font-mono text-sm font-medium text-text">{props.name}</span>
            <span className="text-2xs text-text-subtle">{marker}</span>
          </p>
          {props.description ? (
            <p className="mt-0.5 text-xs text-text-muted">{props.description}</p>
          ) : null}
        </div>
        <div data-testid="file-editor-actions" className="flex flex-wrap items-center gap-2">
          {props.filePath ? <FileActions filePath={props.filePath} /> : null}
          {draft.editing ? (
            <>
              <Button variant="ghost" size="sm" onClick={revert} disabled={draft.saving}>
                {t("agents.configTab.revert")}
              </Button>
              <Button
                size="sm"
                onClick={draft.save}
                disabled={!draft.dirty || draft.saving || invalid}
              >
                {draft.saving ? t("common.saving") : t("common.save")}
              </Button>
            </>
          ) : showMissing ? null : (
            <Button variant="outline" size="sm" onClick={draft.startEditing}>
              {t("common.edit")}
            </Button>
          )}
        </div>
      </div>

      {draft.conflict ? (
        <ConfigStalePanel
          name={props.name}
          draft={draft.value}
          onDiscardAndReload={() => void draft.discardAndReload()}
        />
      ) : draft.error ? (
        <p
          role="alert"
          className="shrink-0 rounded-md border border-danger bg-danger-soft px-3 py-2 text-xs text-danger"
        >
          {translateApiError(t, draft.error)}
        </p>
      ) : null}

      {showMissing ? (
        <ConfigMissingPanel name={props.name} agentName={props.agentName} onCreate={create} />
      ) : draft.editing ? (
        <textarea
          aria-label={t("agents.config.editorLabel", { key: props.name })}
          className="min-h-0 w-full flex-1 resize-none rounded-lg border border-border bg-code p-3 font-mono text-xs leading-[1.6] text-text outline-none transition-colors duration-fast focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent-soft"
          value={draft.value}
          spellCheck={false}
          onChange={(e) => draft.setDraft(e.target.value)}
        />
      ) : (
        <CodeView
          value={props.loading ? "" : props.content}
          filename={props.filePath ?? props.name}
          fill
          ariaLabel={t("agents.config.editorLabel", { key: props.name })}
          className="bg-surface-sunken"
        />
      )}

      <div className="shrink-0 space-y-0.5 text-2xs text-text-subtle">
        <p className="flex flex-wrap gap-x-3">
          {formatLine ? (
            <span className={cn(invalid && "text-danger")} role={invalid ? "status" : undefined}>
              {formatLine}
            </span>
          ) : null}
          <span>{note}</span>
        </p>
        {props.filePath ? <p className="break-all font-mono">{props.filePath}</p> : null}
      </div>

      <ConfirmDialog
        open={confirmRevert}
        onOpenChange={setConfirmRevert}
        title={t("common.discardChanges.title")}
        description={t("common.discardChanges.body")}
        confirmLabel={t("common.discardChanges.confirm")}
        onConfirm={() => {
          setConfirmRevert(false);
          draft.cancel();
        }}
      />
    </div>
  );
}
