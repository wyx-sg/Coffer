// frontend/src/components/memory/MemoryEditor.tsx — the body editor of one memory.
//
// Spec memory "Edit a memory in the web UI or on disk": the body alone is
// edited; the frontmatter (title, provenance) is never in the textarea, so a
// save sends the body with the fingerprint the read carried. A save refused
// as changed (409 `MEMORY_NOTE_CONFLICT`) puts the knowledge editor's conflict
// banner over the text — Compare, Copy my text, Reload… — and Save stays off
// until the person has compared, saved over or reloaded. The draft lives in
// MemoryPane (useFileDraft), so the pane's header can carry Discard and Save.
//
// ⌘S / Ctrl+S saves and Escape discards while the textarea has focus.
import { FileConflictBanner } from "@/components/FileConflictBanner";
import { translateApiError } from "@/lib/api/errors";
import type { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useTranslation } from "react-i18next";

interface Props {
  title: string;
  draft: ReturnType<typeof useFileDraft>;
  /** The banner's sentence, saying the text is not saved. */
  conflictText: string;
  onCompare: () => void;
  onCopyMine: () => void;
  /** Take the disk's version, dropping the draft (asked first, by the banner). */
  onReload: () => void;
  /** Discard, asking first when the draft has changes. */
  onDiscard: () => void;
}

export function MemoryEditor({
  title,
  draft,
  conflictText,
  onCompare,
  onCopyMine,
  onReload,
  onDiscard,
}: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2.5">
      {draft.conflict ? (
        <FileConflictBanner
          title={t("memory.editor.conflictTitle")}
          text={conflictText}
          onCompare={onCompare}
          onCopyMine={onCopyMine}
          onReload={onReload}
        />
      ) : draft.error ? (
        <p role="alert" className="shrink-0 text-sm text-danger">
          {translateApiError(t, draft.error)}
        </p>
      ) : null}
      <textarea
        aria-label={t("memory.editor.label", { title })}
        className="min-h-0 w-full flex-1 resize-none rounded-lg border border-border bg-surface-raised px-4 py-3.5 font-mono text-xs leading-[1.7] text-text outline-none"
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
  );
}
