// frontend/src/components/knowledge/KnowledgeDocumentEditor.tsx
//
// The body-only editor (boards 5.1.03, 5.1.04; spec knowledge "Present a
// collection as one tree in the web UI", "Save a document edited in the web
// UI"). The title and description are the document's frontmatter: a read-only
// key / value grid above the text, "Kept by curation" top right — curation
// keeps them current — and never in the textarea, so a save sends the body
// alone with the fingerprint the read carried. Discard and Save, and the
// unsaved state, sit in the pane's bar (KnowledgeDocumentPane owns the draft).
//
// A save refused as stale (409 `KNOWLEDGE_FILE_CONFLICT`) puts a danger banner
// over the text — what changed and that the text is not saved — with three
// ways out: Compare (the in-page KnowledgeCompareView), Copy my text and
// Reload… (take what is on disk, after asking, because it drops the draft).
// There is no second save over it from here: Save stays off until the person
// has compared, saved over or reloaded.
//
// ⌘S / Ctrl+S saves and Escape discards while the textarea has focus — keys on
// the editor, not global handlers; the buttons' tooltips name them.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { translateApiError } from "@/lib/api/errors";
import type { FileOut } from "@/lib/api/knowledge";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";

interface Props {
  file: FileOut;
  draft: ReturnType<typeof useFileDraft>;
  /** The conflict banner's sentence, built by the pane from what it knows. */
  conflictText: string;
  onCompare: () => void;
  onCopyMine: () => void;
  /** Take the disk's version, dropping the draft (asked first, here). */
  onReload: () => void;
  /** Discard, asking first when the draft has changes. */
  onDiscard: () => void;
}

export function KnowledgeDocumentEditor({
  file,
  draft,
  conflictText,
  onCompare,
  onCopyMine,
  onReload,
  onDiscard,
}: Props) {
  const { t } = useTranslation();
  const [confirmReload, setConfirmReload] = useState(false);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5 px-8 pb-4 pt-5">
      {draft.conflict ? (
        <div
          role="alert"
          className="flex shrink-0 items-center gap-2.5 rounded-lg bg-danger-soft px-3 py-2.5"
        >
          <AlertTriangle className="size-[15px] shrink-0 text-danger" aria-hidden />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <p className="text-sm font-semibold">{t("knowledge.editor.conflictTitle")}</p>
            <p className="text-xs text-text-muted">{conflictText}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Button variant="outline" size="sm" onClick={onCompare}>
              {t("knowledge.editor.compare")}
            </Button>
            <Button variant="outline" size="sm" onClick={onCopyMine}>
              {t("knowledge.editor.copyMine")}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-danger"
              onClick={() => setConfirmReload(true)}
            >
              {t("knowledge.editor.reloadAsk")}
            </Button>
          </div>
        </div>
      ) : draft.error ? (
        <p role="alert" className="shrink-0 text-sm text-danger">
          {translateApiError(t, draft.error)}
        </p>
      ) : null}

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border">
        <dl className="grid shrink-0 grid-cols-[96px_minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-1 border-b border-border-subtle bg-surface-sunken px-4 py-2.5">
          <dt className="font-mono text-2xs text-text-subtle">title</dt>
          <dd className="text-xs text-text">{file.title}</dd>
          <span className="inline-flex items-center gap-1 whitespace-nowrap text-2xs text-text-subtle">
            <Lock className="size-3" aria-hidden />
            {t("knowledge.editor.keptByCuration")}
          </span>
          <dt className="font-mono text-2xs text-text-subtle">description</dt>
          <dd className="text-xs text-text">{file.description}</dd>
        </dl>
        <textarea
          aria-label={t("knowledge.editor.label", { path: file.path })}
          className="min-h-0 w-full flex-1 resize-none bg-surface-raised px-4 py-3.5 font-mono text-xs leading-[1.7] text-text outline-none"
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
              onDiscard();
            }
          }}
        />
      </div>
      {!draft.conflict ? (
        <p className="shrink-0 text-xs text-text-muted">{t("knowledge.editor.editStands")}</p>
      ) : null}

      <ConfirmDialog
        open={confirmReload}
        onOpenChange={setConfirmReload}
        title={t("knowledge.editor.reloadTitle")}
        description={t("knowledge.editor.reloadBody")}
        confirmLabel={t("knowledge.editor.reloadConfirm")}
        onConfirm={() => {
          setConfirmReload(false);
          onReload();
        }}
      />
    </div>
  );
}
