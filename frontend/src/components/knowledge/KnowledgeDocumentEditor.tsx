// frontend/src/components/knowledge/KnowledgeDocumentEditor.tsx
//
// The body-only editor (spec knowledge "Present a collection as one tree in
// the web UI", "Save a document edited in the web UI"). The title and
// description are the document's frontmatter: shown above as read-only
// metadata — curation keeps them current — and never in the textarea, so a
// save sends the body alone with the fingerprint the read carried.
//
// A save refused as stale (409 `KNOWLEDGE_FILE_CONFLICT`) says the document
// changed on disk and the text was not saved, and offers exactly three ways
// out: Reload (take what is on disk), Compare (the disk against the draft,
// from the body the refusal carried) and Copy my text. There is no second save
// over it: Save stays off until the person has reloaded.
//
// ⌘S / Ctrl+S saves and Escape cancels while the textarea has focus — keys on
// the editor, not global handlers.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

import { KnowledgeCompareDialog } from "@/components/knowledge/KnowledgeCompareDialog";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { ApiError, translateApiError } from "@/lib/api/errors";
import type { FileOut } from "@/lib/api/knowledge";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";

interface Props {
  file: FileOut;
  draft: ReturnType<typeof useFileDraft>;
}

/** The body on disk now, as the stale-save refusal carried it. */
function currentBodyOf(error: unknown): string | null {
  if (!(error instanceof ApiError)) return null;
  const details = error.details as { current_body?: unknown } | undefined;
  return typeof details?.current_body === "string" ? details.current_body : null;
}

export function KnowledgeDocumentEditor({ file, draft }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [comparing, setComparing] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const onDisk = draft.conflict ? (currentBodyOf(draft.error) ?? file.body) : null;

  const cancel = () => (draft.dirty ? setConfirmDiscard(true) : draft.cancel());
  const copyMine = () =>
    void navigator.clipboard.writeText(draft.value).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("knowledge.editor.copyFailed")),
    );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 items-center justify-end gap-2">
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
      </div>

      {draft.conflict ? (
        <div
          role="alert"
          className="shrink-0 space-y-2 rounded-md border border-warning bg-warning-soft px-3 py-2 text-sm"
        >
          <p className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="size-4 shrink-0 text-warning" aria-hidden />
            {t("knowledge.editor.conflictTitle")}
          </p>
          <p className="text-text-muted">{t("knowledge.editor.conflictBody")}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setComparing(true)}>
              {t("knowledge.editor.compare")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => void draft.discardAndReload()}>
              {t("knowledge.editor.reload")}
            </Button>
            <Button variant="outline" size="sm" onClick={copyMine}>
              {t("knowledge.editor.copyMine")}
            </Button>
          </div>
        </div>
      ) : draft.error ? (
        <p role="alert" className="shrink-0 text-sm text-danger">
          {translateApiError(t, draft.error)}
        </p>
      ) : null}

      <dl className="grid shrink-0 grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-md bg-surface-sunken px-3 py-2 text-xs">
        <dt className="text-text-subtle">{t("knowledge.editor.title")}</dt>
        <dd className="text-text">{file.title}</dd>
        <dt className="text-text-subtle">{t("knowledge.editor.description")}</dt>
        <dd className="text-text">{file.description}</dd>
        <dt className="col-span-2 text-text-subtle">{t("knowledge.editor.frontmatterNote")}</dt>
      </dl>

      <textarea
        aria-label={t("knowledge.editor.label", { path: file.path })}
        className="min-h-0 w-full flex-1 resize-none rounded-lg border border-border bg-code p-3 font-mono text-xs leading-[1.6] text-text outline-none focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent-soft"
        value={draft.value}
        spellCheck={false}
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
      <p className="shrink-0 text-2xs text-text-subtle">
        {draft.conflict
          ? t("knowledge.editor.footerNotSaved")
          : draft.dirty
            ? t("knowledge.editor.footerUnsaved")
            : t("knowledge.editor.footer")}
      </p>

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
