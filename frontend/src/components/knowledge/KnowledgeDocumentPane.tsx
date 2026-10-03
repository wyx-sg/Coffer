// frontend/src/components/knowledge/KnowledgeDocumentPane.tsx
//
// One open document (boards 5.1.01–5.1.06, 5.1.21): the bar — where it is
// (collection › folders › file), its two tabs, Document (the default, the
// reader and the body editor) and History (every version, who wrote it, its
// diff, restore; spec web-ui "Show a knowledge document's history on its
// History tab"), and the tab's actions: Edit and the ⋯ menu while reading,
// Cancel and Save while editing. The tab is in the path
// (`/knowledge/<uid>/history?file=`); a History that cannot be read leaves the
// Document tab working, because each tab reads on its own.
//
// The draft lives here rather than in the editor so the bar can carry the
// editor's Cancel and Save, as the boards draw them.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Pencil } from "lucide-react";

import { KnowledgeDeleteDocument } from "@/components/knowledge/KnowledgeDeleteDocument";
import { KnowledgeDocumentEditor } from "@/components/knowledge/KnowledgeDocumentEditor";
import { KnowledgeDocumentReader } from "@/components/knowledge/KnowledgeDocumentReader";
import { KnowledgeHistoryTab } from "@/components/knowledge/KnowledgeHistoryTab";
import { KnowledgePaneBar, PaneBarTab, type Crumb } from "@/components/knowledge/KnowledgePaneBar";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut, FileOut } from "@/lib/api/knowledge";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useKnowledgeFile, useSaveKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  /** Knowledge-root-relative path of the open document. */
  path: string;
  tab: "document" | "history";
}

function crumbsOf(collection: CollectionOut, path: string): Crumb[] {
  const parts = pathInCollection(path).split("/");
  return [
    { label: collection.name, to: collectionPath(collection.uid), mono: true },
    ...parts.map((p) => ({ label: p, mono: true })),
  ];
}

export function KnowledgeDocumentPane({ collection, path, tab }: Props) {
  const { t } = useTranslation();
  const file = useKnowledgeFile(path);
  const history = useDocumentHistory(path);
  const count = history.data?.versions.length;

  const tabs = (
    <nav
      aria-label={t("knowledge.document.views")}
      className="ml-[18px] flex gap-[18px] self-stretch"
    >
      <PaneBarTab
        to={collectionPath(collection.uid, "document", path)}
        current={tab === "document"}
      >
        {t("knowledge.document.tab")}
      </PaneBarTab>
      <PaneBarTab to={collectionPath(collection.uid, "history", path)} current={tab === "history"}>
        {t("knowledge.history.tab")}
        {count ? <span className="text-2xs text-text-subtle">{count}</span> : null}
      </PaneBarTab>
    </nav>
  );

  if (!file.data) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <KnowledgePaneBar crumbs={crumbsOf(collection, path)} tabs={tabs} />
        <div className="px-10 py-6">
          {file.error ? (
            <p className="text-sm text-danger" role="alert">
              {translateApiError(t, file.error)}
            </p>
          ) : (
            <div className="space-y-3" aria-busy>
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    // Keyed by path: a draft belongs to one document only.
    <LoadedDocument
      key={file.data.path}
      collection={collection}
      file={file.data}
      tab={tab}
      tabs={tabs}
      reload={() => file.refetch()}
    />
  );
}

interface LoadedProps {
  collection: CollectionOut;
  file: FileOut;
  tab: "document" | "history";
  tabs: ReactNode;
  reload: () => Promise<unknown>;
}

function LoadedDocument({ collection, file, tab, tabs, reload }: LoadedProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const saveFile = useSaveKnowledgeFile();
  const [deleting, setDeleting] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [openItem, revealItem] = useFileActionItems(file.file_path);
  const draft = useFileDraft({
    loaded: file.body,
    fingerprint: file.fingerprint,
    save: (body, expected) =>
      saveFile({ path: file.path, body, expected_fingerprint: expected ?? "" }),
    reload,
    guard: { file: file.path.split("/").pop() ?? file.path, owner: collection.name },
  });
  const name = file.path.split("/").pop() ?? file.path;
  const cancel = () => (draft.dirty ? setConfirmDiscard(true) : draft.cancel());

  const actions = draft.editing ? (
    <>
      <Button variant="outline" onClick={cancel} disabled={draft.saving}>
        {t("common.cancel")}
      </Button>
      <Button onClick={draft.save} disabled={!draft.dirty || draft.saving || draft.conflict}>
        {draft.saving ? t("common.saving") : t("common.save")}
      </Button>
    </>
  ) : (
    <>
      <Button variant="outline" onClick={draft.startEditing}>
        <Pencil aria-hidden /> {t("common.edit")}
      </Button>
      <ActionMenu
        label={t("knowledge.document.more", { path: file.path })}
        actions={[
          { key: "open", label: openItem.label, onSelect: openItem.onClick },
          { key: "reveal", label: revealItem.label, onSelect: revealItem.onClick },
          {
            key: "delete",
            label: t("knowledge.deleteDocument.menu"),
            destructive: true,
            separated: true,
            onSelect: () => setDeleting(true),
          },
        ]}
      />
    </>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar crumbs={crumbsOf(collection, file.path)} tabs={tabs} actions={actions} />
      {tab === "history" ? (
        <KnowledgeHistoryTab path={file.path} currentBody={file.body} />
      ) : draft.editing ? (
        <KnowledgeDocumentEditor
          file={file}
          draft={draft}
          confirmDiscard={confirmDiscard}
          setConfirmDiscard={setConfirmDiscard}
          onCancel={cancel}
        />
      ) : (
        <KnowledgeDocumentReader
          file={file}
          onOpen={openItem.onClick}
          onReveal={revealItem.onClick}
          onDelete={() => setDeleting(true)}
        />
      )}
      <KnowledgeDeleteDocument
        open={deleting}
        onOpenChange={setDeleting}
        path={file.path}
        filePath={file.file_path}
        onDeleted={() => {
          toast.success(t("knowledge.deleteDocument.deletedToast", { name }));
          navigate(collectionPath(collection.uid), { state: { deleted: file.path } });
        }}
      />
    </div>
  );
}
