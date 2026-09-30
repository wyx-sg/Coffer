// frontend/src/components/knowledge/KnowledgeDocumentView.tsx
//
// The Document tab: the rendered document, and Edit, which turns it into the
// body-only editor (spec knowledge "Present a collection as one tree in the
// web UI", "Save a document edited in the web UI"). Every document is the same
// here, whoever wrote it last: it can be edited, opened in the person's own
// editor, revealed in their file manager, and deleted (see "Let only a person
// delete a document").
//
// When the newest version is a curation pass, a line above the body says so and
// links to what that pass changed — the answer to "why does this read
// differently than yesterday?".
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Pencil } from "lucide-react";

import { KnowledgeDeleteDocument } from "@/components/knowledge/KnowledgeDeleteDocument";
import { KnowledgeDocumentEditor } from "@/components/knowledge/KnowledgeDocumentEditor";
import { FindableMarkdown } from "@/components/preview/FindableMarkdown";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";
import type { CollectionOut, FileOut } from "@/lib/api/knowledge";
import { useFileActionItems } from "@/lib/fileActionItems";
import { agentLabel } from "@/lib/knowledge/changes";
import { changePath, collectionPath } from "@/lib/knowledge/routes";
import { useFileDraft } from "@/lib/hooks/useFileDraft";
import { useSaveKnowledgeFile } from "@/lib/hooks/useKnowledge";
import { useDocumentHistory } from "@/lib/hooks/useKnowledgeHistory";
import { formatDateTime } from "@/lib/utils";

interface Props {
  collection: CollectionOut;
  file: FileOut;
  reload: () => Promise<unknown>;
}

export function KnowledgeDocumentView({ collection, file, reload }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const saveFile = useSaveKnowledgeFile();
  const history = useDocumentHistory(file.path);
  const [deleting, setDeleting] = useState(false);
  const [openItem, revealItem] = useFileActionItems(file.file_path);
  const draft = useFileDraft({
    loaded: file.body,
    fingerprint: file.fingerprint,
    save: (body, expected) =>
      saveFile({ path: file.path, body, expected_fingerprint: expected ?? "" }),
    reload,
  });

  if (draft.editing) {
    return <KnowledgeDocumentEditor file={file} draft={draft} />;
  }

  const newest = history.data?.versions[0]?.change;
  const curatedLast = newest && newest.writer === "curation" && newest.operation === "pass";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 truncate text-xs text-text-subtle">
          {t("knowledge.document.meta", {
            updated: formatDateTime(file.updated_at),
            created: formatDateTime(file.created_at),
            actor: agentLabel(t, file.actor),
          })}
        </p>
        <Button variant="outline" size="sm" onClick={draft.startEditing}>
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
      </div>

      {curatedLast ? (
        <p className="shrink-0 rounded-md bg-surface-sunken px-3 py-2 text-xs text-text-muted">
          {t("knowledge.document.curatedBanner", {
            agent: agentLabel(t, newest.agent),
            when: formatDateTime(newest.time),
          })}{" "}
          <Link to={changePath(newest.version)} className="text-accent-text hover:underline">
            {t("knowledge.document.seePass")}
          </Link>
        </p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto">
        <FindableMarkdown fill>{file.body}</FindableMarkdown>
      </div>

      <KnowledgeDeleteDocument
        open={deleting}
        onOpenChange={setDeleting}
        path={file.path}
        filePath={file.file_path}
        onDeleted={() => navigate(collectionPath(collection.uid))}
      />
    </div>
  );
}
