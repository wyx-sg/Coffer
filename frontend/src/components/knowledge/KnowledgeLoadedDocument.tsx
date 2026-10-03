// frontend/src/components/knowledge/KnowledgeLoadedDocument.tsx
//
// A document whose file has loaded (boards 5.1.01–5.1.04, 5.1.29): the pane
// bar with its tabs and the tab's actions, and under it the reader, the body
// editor, Compare after a refused save, or History. The draft lives here
// rather than in the editor so the bar can carry the editor's Discard and
// Save, as the boards draw them. While it differs from the saved text the tree
// marks the file (setDirtyDocument) and the shell's leave-without-saving
// prompt guards every way out (useFileDraft → useUnsavedGuard, board 1.1.12).
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeCompareView } from "@/components/knowledge/KnowledgeCompareView";
import { useDeleteDocument } from "@/components/knowledge/KnowledgeDeleteDocument";
import {
  EditingActions,
  ReadingActions,
  type DocumentView,
} from "@/components/knowledge/KnowledgeDocumentActions";
import { KnowledgeDocumentEditor } from "@/components/knowledge/KnowledgeDocumentEditor";
import { KnowledgeDocumentReader } from "@/components/knowledge/KnowledgeDocumentReader";
import { KnowledgeHistoryTab } from "@/components/knowledge/KnowledgeHistoryTab";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut, FileOut } from "@/lib/api/knowledge";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useSaveKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { whenLabel } from "@/lib/knowledge/changes";
import { setDirtyDocument, setEditingDocument } from "@/lib/knowledge/dirtyDocument";
import {
  conflictSentence,
  currentBodyOf,
  currentFingerprintOf,
  diskMeta,
} from "@/lib/knowledge/documentConflict";
import { crumbsOf } from "@/lib/knowledge/crumbs";

interface LoadedProps {
  collection: CollectionOut;
  file: FileOut;
  tab: "document" | "history";
  tabs: ReactNode;
  reload: () => Promise<unknown>;
}

export function KnowledgeLoadedDocument({ collection, file, tab, tabs, reload }: LoadedProps) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const saveFile = useSaveKnowledgeFile();
  const removeDocument = useDeleteDocument(collection.uid);
  const history = useDocumentHistory(file.path);
  const fileActions = useFileActionItems(file.file_path);
  const [view, setView] = useState<DocumentView>("preview");
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [savingOver, setSavingOver] = useState(false);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const draft = useFileDraft({
    loaded: file.body,
    fingerprint: file.fingerprint,
    save: (body, expected) =>
      saveFile({ path: file.path, body, expected_fingerprint: expected ?? "" }),
    reload,
    guard: { file: file.path.split("/").pop() ?? file.path, owner: collection.name },
  });
  const name = file.path.split("/").pop() ?? file.path;
  const markdown = /\.(md|markdown)$/i.test(file.path);
  const discard = () => (draft.dirty ? setConfirmDiscard(true) : draft.cancel());

  // The tree marks the file with an accent dot while its draft is unsaved.
  useEffect(() => {
    if (!draft.dirty) return;
    setDirtyDocument(file.path);
    return () => setDirtyDocument(null);
  }, [draft.dirty, file.path]);
  // The header drops Upload to secondary while the editor is open.
  useEffect(() => {
    if (!draft.editing) return;
    setEditingDocument(file.path);
    return () => setEditingDocument(null);
  }, [draft.editing, file.path]);

  // A refused save: the disk moved, so look up who moved it for the banner.
  const refetchHistory = history.refetch;
  useEffect(() => {
    if (draft.conflict) void refetchHistory();
  }, [draft.conflict, refetchHistory]);
  const newest = history.data?.versions[0]?.change;
  const onDisk = draft.conflict ? (currentBodyOf(draft.error) ?? file.body) : null;

  const copyMine = () =>
    void navigator.clipboard.writeText(draft.value).then(
      () => toast.success(t("knowledge.editor.copied")),
      () => toast.error(t("knowledge.editor.copyFailed")),
    );
  const takeDisk = () => {
    setComparing(false);
    void draft.discardAndReload().then(() => toast.success(t("knowledge.editor.reloaded")));
  };
  // "Save my edit": a second save over the disk's version, naming the
  // fingerprint the refusal carried.
  const saveOver = async () => {
    setSavingOver(true);
    try {
      const fingerprint = currentFingerprintOf(draft.error);
      const fresh =
        fingerprint ?? ((await reload()) as { data?: FileOut } | undefined)?.data?.fingerprint;
      await saveFile({ path: file.path, body: draft.value, expected_fingerprint: fresh ?? "" });
      setComparing(false);
      draft.cancel();
      await reload();
    } catch (error) {
      toast.error(translateApiError(t, error));
    } finally {
      setSavingOver(false);
    }
  };

  const actions = draft.editing ? (
    comparing ? (
      <EditingActions
        dirty
        notSaved
        saving={false}
        onDiscard={discard}
        onSave={draft.save}
        statusOnly
      />
    ) : (
      <EditingActions
        dirty={draft.dirty}
        notSaved={draft.conflict}
        saving={draft.saving}
        onDiscard={discard}
        onSave={draft.save}
      />
    )
  ) : (
    <ReadingActions
      path={file.path}
      // Preview / Source belong to the Document tab; History shows diffs.
      markdown={markdown && tab === "document"}
      view={markdown ? view : "source"}
      onView={setView}
      onEdit={() => {
        setStartedAt(new Date().toISOString());
        draft.startEditing();
      }}
      fileActions={fileActions}
      onDelete={() => removeDocument(file.path)}
    />
  );

  let body: ReactNode;
  if (tab === "history") {
    body = <KnowledgeHistoryTab path={file.path} currentBody={file.body} />;
  } else if (draft.editing && comparing && onDisk !== null) {
    body = (
      <KnowledgeCompareView
        name={name}
        mine={draft.value}
        onDisk={onDisk}
        mineMeta={t("knowledge.compare.mineMeta", {
          when: whenLabel(t, startedAt ?? new Date().toISOString(), i18n.language),
        })}
        diskMeta={diskMeta(t, newest, i18n.language)}
        saving={savingOver}
        onBack={() => setComparing(false)}
        onSaveMine={() => void saveOver()}
        onUseDisk={takeDisk}
      />
    );
  } else if (draft.editing) {
    body = (
      <KnowledgeDocumentEditor
        file={file}
        draft={draft}
        conflictText={conflictSentence(t, newest, name, i18n.language)}
        onCompare={() => setComparing(true)}
        onCopyMine={copyMine}
        onReload={takeDisk}
        onDiscard={discard}
      />
    );
  } else {
    body = <KnowledgeDocumentReader file={file} source={!markdown || view === "source"} />;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar crumbs={crumbsOf(collection, file.path)} tabs={tabs} actions={actions} />
      {body}
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
