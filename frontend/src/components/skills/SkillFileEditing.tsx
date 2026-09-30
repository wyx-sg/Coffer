// frontend/src/components/skills/SkillFileEditing.tsx
// A skill file in edit mode (canvas 4.3.10, 4.3.11): the header says whether
// the text is saved, with Cancel and Save; ⌘S / Ctrl+S saves and Escape
// cancels while the text has focus. A save refused as stale (409
// SKILL_FILE_STALE — the file changed on disk after it was opened, in the
// user's own editor say) keeps the text and offers exactly three ways out, as
// Knowledge does: Reload (take what is on disk), Compare (disk against the
// text) and Copy my text. Save stays off until the reader has reloaded.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { KnowledgeCompareDialog } from "@/components/knowledge/KnowledgeCompareDialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useReadSkillFileNow } from "@/lib/hooks/useSkills";

interface Props {
  uid: string;
  path: string;
  draft: ReturnType<typeof useFileDraft>;
}

export function SkillFileEditing({ uid, path, draft }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const readNow = useReadSkillFileNow();
  const [onDisk, setOnDisk] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const cancel = () => (draft.dirty ? setConfirmDiscard(true) : draft.cancel());
  const copyMine = () =>
    void navigator.clipboard.writeText(draft.value).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("skills.menu.copyFailed")),
    );
  const compare = () =>
    readNow.mutate({ uid, path }, { onSuccess: (file) => setOnDisk(file.content) });

  return (
    <>
      <div className="flex min-h-12 shrink-0 flex-wrap items-center gap-2 border-b border-border-subtle px-4 py-2">
        <span className="min-w-0 truncate font-mono text-xs font-label text-text">{path}</span>
        {draft.conflict ? (
          <span className="text-xs text-danger">{t("skills.files.notSaved")}</span>
        ) : draft.dirty ? (
          <span className="text-xs text-text-muted">
            {t("skills.files.unsaved")}{" "}
            <span className="text-text-subtle">{t("skills.files.saveKey")}</span>
          </span>
        ) : null}
        <span className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={cancel} disabled={draft.saving}>
            {t("common.cancel")}
          </Button>
          <Button
            size="sm"
            onClick={draft.save}
            disabled={!draft.dirty || draft.saving || draft.conflict}
          >
            {draft.saving ? t("common.saving") : t("common.save")}
          </Button>
        </span>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
        {draft.conflict ? (
          <div role="alert" className="flex shrink-0 gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0 text-danger" aria-hidden />
            <div className="flex min-w-0 flex-col gap-1.5">
              <p className="text-sm font-label text-text">{t("skills.files.conflictTitle")}</p>
              <p className="text-xs text-text-muted">{t("skills.files.conflictBody")}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => void draft.discardAndReload()}>
                  {t("knowledge.editor.reload")}
                </Button>
                <Button variant="outline" size="sm" disabled={readNow.isPending} onClick={compare}>
                  {t("knowledge.editor.compare")}
                </Button>
                <Button variant="outline" size="sm" onClick={copyMine}>
                  {t("knowledge.editor.copyMine")}
                </Button>
              </div>
            </div>
          </div>
        ) : draft.error ? (
          <p role="alert" className="shrink-0 text-sm text-danger">
            {translateApiError(t, draft.error)}
          </p>
        ) : null}

        <textarea
          aria-label={t("skills.files.editorLabel", { path })}
          className="min-h-0 w-full flex-1 resize-none rounded-lg border border-border bg-code p-3 font-mono text-xs leading-[1.6] text-text outline-none focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent-soft"
          value={draft.value}
          spellCheck={false}
          autoFocus
          onChange={(e) => draft.setDraft(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
              e.preventDefault();
              if (draft.dirty && !draft.saving && !draft.conflict) draft.save();
            } else if (e.key === "Escape") {
              e.preventDefault();
              cancel();
            }
          }}
        />
      </div>

      {onDisk !== null ? (
        <KnowledgeCompareDialog
          open
          onOpenChange={(open) => !open && setOnDisk(null)}
          onDisk={onDisk}
          mine={draft.value}
        />
      ) : null}
      <ConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title={t("common.discardChanges.title")}
        description={t("common.discardChanges.body")}
        confirmLabel={t("common.discardChanges.confirm")}
        onConfirm={() => {
          setConfirmDiscard(false);
          draft.cancel();
        }}
      />
    </>
  );
}
