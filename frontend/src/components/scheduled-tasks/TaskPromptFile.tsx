// src/components/scheduled-tasks/TaskPromptFile.tsx — an open task's Prompt tab: the prompt as a Markdown file.
//
// It reads like any file Coffer shows (Foundations 0.6.03): the 40px toolbar
// with the file's name and Preview / Source, over the rendered prompt. Edit
// turns the body into the Markdown editor; the toolbar then says the draft is
// unsaved and offers Revert and Save. The file is the task's PROMPT.md, in its
// folder, so it can as well be edited in any editor; Save writes it and returns
// to the preview; a refused save stays in the editor with the daemon's reason.
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

const FILE_NAME = "PROMPT.md";

export function TaskPromptFile({ task }: { task: ScheduledTask }) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const edit = useSetTaskPrompt();
  const [view, setView] = useState<FileView>("preview");
  const [draft, setDraft] = useState<string | null>(null);
  const prompt = task.prompt;
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
    <div className="flex min-h-[320px] flex-col overflow-hidden rounded-lg border border-border-subtle">
      <ViewerToolbar
        path={FILE_NAME}
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
        <div className="p-3">
          <CodeEditor
            value={draft}
            onChange={setDraft}
            language="markdown"
            ariaLabel={FILE_NAME}
            invalid={invalid}
            minHeight="16rem"
            maxHeight="60vh"
          />
        </div>
      ) : (
        <FileBody path={FILE_NAME} text={prompt} view={view} wrap />
      )}
    </div>
  );
}
