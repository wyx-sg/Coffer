// frontend/src/components/agents/ConfigEditorPane.tsx — spec agent-registry.
// Right pane of the agent's Config files tab (boards 2.1.40–2.1.45): the viewer
// toolbar (path; Preview / Source for Markdown; Open in editor, Reveal, Edit —
// or, while editing, "● Unsaved changes" with Revert and Save), the file, and
// a status line: its format, whether the draft parses, and what the file is for.
//
// Reading is the default: these are the agent's real configuration, so a pane
// opened to look cannot be changed by a stray keystroke. A JSON draft is
// checked as it is typed — the line where it stops parsing is marked in the
// text and Save waits until it parses (the daemon refuses malformed JSON
// anyway). A save refused because the file changed on disk keeps the draft
// ("● Not saved", ConfigStalePanel); a file the agent has not created yet shows
// the empty state that creates it (ConfigMissingPanel). All state is the
// parent's draft.
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, CircleAlert, Pencil } from "lucide-react";

import { ConfigMissingPanel, ConfigStalePanel } from "@/components/agents/ConfigEditorNotices";
import { FileBody } from "@/components/files/FileBody";
import { LineEditor } from "@/components/files/LineEditor";
import { isMarkdownPath } from "@/components/files/middlePath";
import { DraftStatus, ViewerToolbar, type FileView } from "@/components/files/ViewerToolbar";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { checkJson } from "@/lib/agents/configFiles";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConfigFileInfo } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";

export interface ConfigEditorPaneProps {
  /** The file's own name (`settings.json`, or a directory file's relpath). */
  name: string;
  /** Absolute on-disk path (external-editor actions and the toolbar). */
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

function StatusLine({
  format,
  check,
  description,
}: {
  format: ConfigFileInfo["format"] | undefined;
  check: ReturnType<typeof checkJson> | null;
  description?: string | null;
}) {
  const { t } = useTranslation();
  const dot = (
    <span aria-hidden className="text-border">
      ·
    </span>
  );
  return (
    <p className="flex h-[30px] shrink-0 items-center gap-2.5 border-t border-border-subtle px-3 text-xs text-text-muted">
      {format ? <span>{FORMAT_LABEL[format]}</span> : null}
      {check ? (
        <>
          {dot}
          {check.ok ? (
            <span role="status" className="inline-flex items-center gap-1 text-success">
              <Check className="size-3" aria-hidden /> {t("agents.configTab.validJson")}
            </span>
          ) : (
            <span role="status" className="inline-flex items-center gap-1 text-danger">
              <CircleAlert className="size-3" aria-hidden /> {t("agents.configTab.invalidJson")}
            </span>
          )}
        </>
      ) : null}
      {description ? (
        <>
          {check ? null : dot}
          <span className={check ? "ml-auto truncate" : "truncate"}>{description}</span>
        </>
      ) : null}
    </p>
  );
}

export function ConfigEditorPane(props: ConfigEditorPaneProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { draft } = props;
  const [confirmRevert, setConfirmRevert] = useState(false);
  const [view, setView] = useState<FileView>("preview");

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
  const shownPath = abbreviateHomePath(props.filePath ?? props.name);
  const markdown = isMarkdownPath(props.name) && !draft.editing && !showMissing;

  const create = () => {
    draft.startEditing();
    if (props.format === "json") draft.setDraft("{}\n");
  };
  const revert = () => (draft.dirty ? setConfirmRevert(true) : draft.cancel());
  const save = () => {
    if (draft.dirty && !draft.saving && !invalid && !draft.conflict) draft.save();
  };

  return (
    <>
      <ViewerToolbar
        path={shownPath}
        absPath={showMissing || draft.editing ? undefined : props.filePath}
        reveal
        view={markdown ? { value: view, onChange: setView } : undefined}
        status={
          draft.editing && (draft.conflict || draft.dirty) ? (
            <DraftStatus notSaved={draft.conflict} />
          ) : null
        }
      >
        {draft.editing ? (
          <>
            <Button
              variant="ghost"
              size="sm"
              className="text-text"
              onClick={revert}
              disabled={draft.saving}
            >
              {t("agents.configTab.revert")}
            </Button>
            <Button
              size="sm"
              onClick={save}
              disabled={!draft.dirty || draft.saving || invalid || draft.conflict}
            >
              {draft.saving ? t("common.saving") : t("common.save")}
            </Button>
          </>
        ) : showMissing ? null : (
          <Button variant="outline" size="sm" onClick={draft.startEditing}>
            <Pencil aria-hidden /> {t("common.edit")}
          </Button>
        )}
      </ViewerToolbar>

      {draft.conflict ? (
        <ConfigStalePanel
          name={props.name}
          draft={draft.value}
          onDiscardAndReload={() => void draft.discardAndReload()}
        />
      ) : draft.error ? (
        <p
          role="alert"
          className="m-3 shrink-0 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger"
        >
          {translateApiError(t, draft.error)}
        </p>
      ) : null}

      {showMissing ? (
        <ConfigMissingPanel name={props.name} agentName={props.agentName} onCreate={create} />
      ) : draft.editing ? (
        <LineEditor
          ariaLabel={t("agents.config.editorLabel", { key: props.name })}
          value={draft.value}
          onChange={draft.setDraft}
          error={
            json && !json.ok
              ? {
                  line: json.line,
                  message: t("agents.configTab.invalidAt", {
                    line: json.line,
                    column: json.column,
                  }),
                }
              : null
          }
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
              e.preventDefault();
              save();
            }
          }}
        />
      ) : props.loading ? (
        <div className="space-y-2 p-4" aria-busy="true">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <FileBody path={props.name} text={props.content} view={view} />
      )}

      <StatusLine format={props.format} check={json} description={props.description} />

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
    </>
  );
}
