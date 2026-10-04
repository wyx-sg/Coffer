// frontend/src/components/knowledge/KnowledgeDocumentEditor.tsx
//
// The body-only editor (boards 5.1.03, 5.1.04; spec knowledge "Show a
// collection as one tree of documents in the web UI", "Save a document edited
// in the web UI"). The title and description are the document's frontmatter: a
// read-only key / value grid above the text, never in the textarea, so a save
// sends the body alone with the fingerprint the read carried. Discard and Save, and the
// unsaved state, sit in the pane's bar (KnowledgeDocumentPane owns the draft).
//
// A save refused as stale (409 `KNOWLEDGE_FILE_CONFLICT`) puts a danger banner
// over the text — what changed and that the text is not saved — with three
// ways out (FileConflictBanner): Compare (the in-page KnowledgeCompareView),
// Copy my text and Reload… (take what is on disk, after asking, because it
// drops the draft).
// There is no second save over it from here: Save stays off until the person
// has compared, saved over or reloaded.
//
// ⌘S / Ctrl+S saves and Escape discards while the textarea has focus — keys on
// the editor, not global handlers; the buttons' tooltips name them.
import { useTranslation } from "react-i18next";

import { FileTextEditor } from "@/components/files/FileTextEditor";
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

  return (
    <FileTextEditor
      className="px-8 pb-4 pt-5"
      value={draft.value}
      onChange={draft.setDraft}
      ariaLabel={t("knowledge.editor.label", { path: file.path })}
      isConflict={draft.conflict}
      dirty={draft.dirty}
      saving={draft.saving}
      error={draft.error}
      conflict={{
        title: t("knowledge.editor.conflictTitle"),
        text: conflictText,
        onCompare,
        onCopyMine,
        onReload,
      }}
      header={
        <dl className="grid shrink-0 grid-cols-[96px_minmax(0,1fr)] items-baseline gap-x-3 gap-y-1 border-b border-border-subtle bg-surface-sunken px-4 py-2.5">
          <dt className="font-mono text-2xs text-text-subtle">title</dt>
          <dd className="text-xs text-text">{file.title}</dd>
          <dt className="font-mono text-2xs text-text-subtle">description</dt>
          <dd className="text-xs text-text">{file.description}</dd>
        </dl>
      }
      onSave={draft.save}
      onDiscard={onDiscard}
    />
  );
}
