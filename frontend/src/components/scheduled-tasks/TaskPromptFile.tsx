// src/components/scheduled-tasks/TaskPromptFile.tsx — PROMPT.md open in a task's Files tab: the one file the page edits.
//
// It reads like any file Coffer shows (Foundations 0.6.03): the 40px toolbar
// with the file's path and Preview / Source, Open in editor and Reveal, over
// the rendered prompt, filling the Files card's right pane. Edit turns the body
// into the Markdown editor; the toolbar then says the draft is unsaved and
// offers Revert and Save. The file is in the task's folder, so it can as well
// be edited in any editor; Save writes it and returns to the preview; a refused
// save stays in the editor with the daemon's reason.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";

import { FileBody } from "@/components/files/FileBody";
import { ViewerToolbar, type FileView } from "@/components/files/ViewerToolbar";
import { CodeEditor } from "@/components/preview/CodeEditor";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { ScheduledTask } from "@/lib/api/scheduledTasks";
import { useSetTaskPrompt } from "@/lib/hooks/useScheduledTasks";
import { PROMPT_MAX_LENGTH } from "@/lib/scheduledTasks/format";

export const PROMPT_FILE = "PROMPT.md";

export function TaskPromptFile({ task }: { task: ScheduledTask }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const edit = useSetTaskPrompt();
  const [view, setView] = useState<FileView>("preview");
  const prompt = task.prompt;
  // A task not yet given its prompt opens straight in the editor.
  const [draft, setDraft] = useState<string | null>(() => (prompt.trim() ? null : ""));
  const editing = draft !== null;
  const dirty = editing && draft !== prompt;
  const invalid = editing && (draft.trim() === "" || draft.length > PROMPT_MAX_LENGTH);

  const save = () => {
    if (!editing || invalid || edit.isPending) return;
    edit.mutate(
      { uid: task.uid, prompt: draft },
      {
        onSuccess: () => setDraft(null),
        onError: (error) => toast.error(translateApiError(t, error)),
      },
    );
  };

  return (
    <>
      <ViewerToolbar
        path={`${task.name}/${PROMPT_FILE}`}
        absPath={editing || !task.folder ? undefined : `${task.folder}/${PROMPT_FILE}`}
        reveal
        size={new Blob([editing ? draft : prompt]).size}
        view={editing ? undefined : { value: view, onChange: setView }}
        status={
          dirty ? (
            <span className="text-xs text-text-muted">● {t("scheduledTasks.prompt.unsaved")}</span>
          ) : null
        }
      >
        {editing ? (
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => setDraft(null)}>
              {dirty ? t("scheduledTasks.prompt.revert") : t("common.cancel")}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!dirty || invalid || edit.isPending}
              onClick={save}
            >
              {t("common.save")}
            </Button>
          </>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label={t("scheduledTasks.prompt.edit")}
            onClick={() => setDraft(prompt)}
          >
            <Pencil aria-hidden /> {t("common.edit")}
          </Button>
        )}
      </ViewerToolbar>
      {editing ? (
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <CodeEditor
            value={draft}
            onChange={setDraft}
            language="markdown"
            ariaLabel={PROMPT_FILE}
            invalid={invalid}
            minHeight="16rem"
            maxHeight="none"
          />
        </div>
      ) : (
        <FileBody path={PROMPT_FILE} text={prompt} view={view} wrap />
      )}
    </>
  );
}
