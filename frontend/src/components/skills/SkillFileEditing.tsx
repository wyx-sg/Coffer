// frontend/src/components/skills/SkillFileEditing.tsx
// A skill file in edit mode (canvas 4.3.13 editing, 4.3.14 conflict, 4.3.40
// leave guard): the toolbar says whether the text is saved, with Cancel and
// Save; ⌘S / Ctrl+S saves and Escape cancels while the text has focus.
// Cancelling a changed file asks "Discard your edit to SKILL.md?" — the same
// question the shell's leave-without-saving prompt asks on a route change.
//
// A save refused as stale (409 SKILL_FILE_STALE — the file changed on disk after
// it was opened, in the person's own editor say) keeps the text and offers two
// ways to settle it: Compare… opens the 1060 two-way choice — Keep my edit
// (saved over the file, naming the fingerprint just read) or Take the version
// on disk (the file reloads, the edit is dropped) — and Copy my text. Save stays
// off until one of them is done.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";

import { FileTextEditor } from "@/components/files/FileTextEditor";
import { ViewerToolbar } from "@/components/files/ViewerToolbar";
import { SkillFileConflict } from "@/components/skills/SkillFileConflict";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Kbd } from "@/components/ui/kbd";
import { useToast } from "@/components/ui/toast";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useReadSkillFileNow } from "@/lib/hooks/useSkills";

interface Props {
  uid: string;
  /** The skill's name. */
  owner: string;
  path: string;
  draft: ReturnType<typeof useFileDraft>;
  /** Re-reads the file after a save over the disk's version. */
  reload: () => Promise<unknown>;
}

export function SkillFileEditing({ uid, owner, path, draft, reload }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const readNow = useReadSkillFileNow();
  const [onDisk, setOnDisk] = useState<{ text: string; fingerprint: string } | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const name = path.split("/").pop() ?? path;
  const cancel = () => (draft.dirty ? setConfirmDiscard(true) : draft.cancel());
  const copyMine = () =>
    void navigator.clipboard.writeText(draft.value).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("skills.menu.copyFailed")),
    );
  const compare = () =>
    readNow.mutate(
      { uid, path },
      { onSuccess: (file) => setOnDisk({ text: file.content, fingerprint: file.fingerprint }) },
    );

  const status = draft.conflict ? (
    <span className="whitespace-nowrap text-xs text-danger">{t("skills.files.notSaved")}</span>
  ) : draft.dirty ? (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
      {t("skills.files.unsaved")}
      <Kbd>⌘S</Kbd>
    </span>
  ) : null;

  return (
    <>
      <ViewerToolbar path={`${owner}/${path}`} status={status}>
        <Button variant="ghost" size="sm" onClick={cancel} disabled={draft.saving}>
          {t("common.cancel")}
        </Button>
        <Button
          size="sm"
          onClick={draft.save}
          loading={draft.saving}
          disabled={!draft.dirty || draft.conflict}
        >
          {t("common.save")}
        </Button>
      </ViewerToolbar>

      <FileTextEditor
        className="p-3"
        variant="code"
        value={draft.value}
        onChange={draft.setDraft}
        ariaLabel={t("skills.files.editorLabel", { path })}
        isConflict={draft.conflict}
        dirty={draft.dirty}
        saving={draft.saving}
        error={draft.error}
        onSave={draft.save}
        onDiscard={cancel}
        banner={
          <div role="alert" className="flex shrink-0 gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5">
            <AlertCircle className="mt-0.5 size-[15px] shrink-0 text-danger" aria-hidden />
            <div className="flex min-w-0 flex-col gap-1.5">
              <p className="text-sm font-label text-text">
                {t("skills.files.conflictTitle", { file: name })}
              </p>
              <p className="text-xs text-text-muted">{t("skills.files.conflictBody")}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" loading={readNow.isPending} onClick={compare}>
                  {t("skills.files.compare")}
                </Button>
                <Button variant="ghost" size="sm" onClick={copyMine}>
                  {t("skills.files.copyMine")}
                </Button>
              </div>
            </div>
          </div>
        }
      />

      {onDisk ? (
        <SkillFileConflict
          uid={uid}
          owner={owner}
          path={path}
          mine={draft.value}
          disk={onDisk}
          onClose={() => setOnDisk(null)}
          onTakeDisk={() => {
            setOnDisk(null);
            void draft.discardAndReload();
          }}
          onSavedOver={() => {
            setOnDisk(null);
            draft.cancel();
            void reload();
          }}
        />
      ) : null}
      <ConfirmDialog
        open={confirmDiscard}
        onOpenChange={setConfirmDiscard}
        title={t("skills.files.discardTitle", { file: name })}
        description={t("skills.files.discardBody", { file: name, owner })}
        confirmLabel={t("skills.files.discardConfirm")}
        cancelLabel={t("skills.files.keepEditing")}
        onConfirm={() => {
          setConfirmDiscard(false);
          draft.cancel();
        }}
      />
    </>
  );
}
