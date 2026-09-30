// frontend/src/components/knowledge/KnowledgeDocumentEditor.tsx
//
// The body-only editor (boards 5.1.05, 5.1.06; spec knowledge "Present a
// collection as one tree in the web UI", "Save a document edited in the web
// UI"). The title and description are the document's frontmatter: shown in
// the editor's head as read-only metadata — curation keeps them current — and
// never in the textarea, so a save sends the body alone with the fingerprint
// the read carried. Cancel and Save sit in the pane's bar
// (KnowledgeDocumentPane owns the draft).
//
// A save refused as stale (409 `KNOWLEDGE_FILE_CONFLICT`) says the document
// changed on disk and the text was not saved, and offers exactly three ways
// out: Compare (the disk against the draft, from the body the refusal
// carried), Reload (take what is on disk) and Copy my text. There is no second
// save over it: Save stays off until the person has reloaded.
//
// ⌘S / Ctrl+S saves and Escape cancels while the textarea has focus — keys on
// the editor, not global handlers.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { KnowledgeCompareDialog } from "@/components/knowledge/KnowledgeCompareDialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Kbd } from "@/components/ui/kbd";
import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { FileOut } from "@/lib/api/knowledge";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";

interface Props {
  file: FileOut;
  draft: ReturnType<typeof useFileDraft>;
  confirmDiscard: boolean;
  setConfirmDiscard: (open: boolean) => void;
  /** Cancel, asking first when the draft has changes. */
  onCancel: () => void;
}

/** The body on disk now, as the stale-save refusal carried it. */
function currentBodyOf(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const details = error.details as { current_body?: unknown } | undefined;
  return typeof details?.current_body === "string" ? details.current_body : null;
}

export function KnowledgeDocumentEditor({
  file,
  draft,
  confirmDiscard,
  setConfirmDiscard,
  onCancel,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [comparing, setComparing] = useState(false);
  const onDisk = draft.conflict ? (currentBodyOf(draft.error) ?? file.body) : null;

  const copyMine = () =>
    void navigator.clipboard.writeText(draft.value).then(
      () => toast.success(t("knowledge.editor.copied")),
      () => toast.error(t("knowledge.editor.copyFailed")),
    );
  const reload = () =>
    void draft.discardAndReload().then(() => toast.success(t("knowledge.editor.reloaded")));

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {draft.conflict ? (
        <div className="shrink-0 px-6 pt-4">
          <div
            role="alert"
            className="flex flex-wrap items-start gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
          >
            <AlertTriangle className="mt-px size-3.5 shrink-0 text-danger" aria-hidden />
            <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
              <p className="text-sm font-label">{t("knowledge.editor.conflictTitle")}</p>
              <p className="text-xs leading-[1.45] text-text-muted">
                {t("knowledge.editor.conflictBody")}
              </p>
            </div>
            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              <Button variant="outline" size="sm" onClick={() => setComparing(true)}>
                {t("knowledge.editor.compare")}
              </Button>
              <Button variant="outline" size="sm" onClick={reload}>
                {t("knowledge.editor.reload")}
              </Button>
              <Button variant="outline" size="sm" onClick={copyMine}>
                {t("knowledge.editor.copyMine")}
              </Button>
            </div>
          </div>
        </div>
      ) : draft.error ? (
        <p role="alert" className="shrink-0 px-6 pt-4 text-sm text-danger">
          {translateApiError(t, draft.error)}
        </p>
      ) : null}

      <div className="mx-6 mt-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border">
        <dl className="grid shrink-0 grid-cols-[90px_minmax(0,1fr)] gap-x-3 gap-y-1 border-b border-border-subtle bg-surface-sunken px-[18px] py-2.5 text-xs">
          <dt className="text-text-subtle">{t("knowledge.editor.title")}</dt>
          <dd className="text-text">{file.title}</dd>
          <dt className="text-text-subtle">{t("knowledge.editor.description")}</dt>
          <dd className="text-text">{file.description}</dd>
          <dt className="text-text-subtle">{t("knowledge.editor.frontmatter")}</dt>
          <dd className="text-text-subtle">{t("knowledge.editor.frontmatterNote")}</dd>
        </dl>
        <textarea
          aria-label={t("knowledge.editor.label", { path: file.path })}
          className="min-h-0 w-full flex-1 resize-none bg-surface-raised px-[18px] py-4 font-mono text-[12.5px] leading-[1.7] text-text outline-none"
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
              onCancel();
            }
          }}
        />
      </div>
      {!draft.conflict ? (
        <p className="shrink-0 px-6 pt-2 text-xs text-text-subtle">
          {t("knowledge.editor.editStands")}
        </p>
      ) : null}
      <div className="mt-3 flex h-9 shrink-0 items-center gap-1.5 border-t border-border-subtle px-6 text-xs text-text-muted">
        <span>{t("knowledge.editor.markdown")}</span>
        {draft.conflict || draft.dirty ? (
          <>
            <span className="text-text-subtle">·</span>
            <span className={draft.conflict ? "text-danger" : undefined}>
              {draft.conflict ? t("knowledge.editor.notSaved") : t("knowledge.editor.unsaved")}
            </span>
          </>
        ) : null}
        <span className="text-text-subtle">·</span>
        <Kbd aria-hidden>⌘S</Kbd>
        <span>{t("knowledge.editor.saveKey")}</span>
        <Kbd aria-hidden>esc</Kbd>
        <span>{t("knowledge.editor.cancelKey")}</span>
      </div>

      {onDisk !== null ? (
        <KnowledgeCompareDialog
          open={comparing}
          onOpenChange={setComparing}
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
    </div>
  );
}
