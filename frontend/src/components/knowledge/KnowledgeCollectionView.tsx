// frontend/src/components/knowledge/KnowledgeCollectionView.tsx
//
// A collection with no document open (boards 5.1.10, 5.1.11, 5.1.14). The pane
// bar is the collection's name with a ⋯ menu — Reveal in Finder · Copy path ·
// Rename… (a dialog; the folder moves with the name, board 5.1.31) · Delete
// collection…, which asks first and then offers Undo in a toast; beside it **Tidy**, which
// hands the collection to the default managed agent and sends the prompt at
// once (spec knowledge "Hand a tidy to the agent"). The body is one
// 720-wide page: the folder name as the heading, its description — the opening
// paragraph of its README — edited in place (click, then blur or ⌘Enter saves,
// Esc cancels, and the success toast offers Undo), and its properties
// (KnowledgeStatsLine). A just created, empty collection is the same page with
// one muted line under the properties saying how the first document gets in.
//
// No switch and no reach: every collection is served to every agent (spec
// knowledge "Serve every collection to every agent").
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { KnowledgeDeleteCollection } from "@/components/knowledge/KnowledgeDeleteCollection";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { KnowledgeRenameDialog } from "@/components/knowledge/KnowledgeRenameDialog";
import { KnowledgeStatsLine } from "@/components/knowledge/KnowledgeStatsLine";
import { Textarea } from "@/components/ui/textarea";
import { ActionMenu } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useFsActions } from "@/lib/fsActions";
import { useDescribeCollection } from "@/lib/hooks/useKnowledge";

interface Props {
  collection: CollectionOut;
}

export function KnowledgeCollectionView({ collection }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const [editing, setEditing] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const empty = collection.document_count === 0;

  const revealFolder = () =>
    void reveal(collection.folder_path).catch(() => toast.error(t("fileActions.revealFailed")));
  const copyPath = () =>
    void navigator.clipboard.writeText(collection.folder_path).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("knowledge.collection.copyFailed")),
    );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar
        crumbs={[{ label: collection.name, mono: true }]}
        actions={
          <>
            <AgentHandoff
              prompt={collection.tidy_handoff.prompt}
              label={t("knowledge.tidy.one")}
              size="sm"
              help={false}
            />
            <ActionMenu
              label={t("knowledge.collection.more", { name: collection.name })}
              actions={[
                {
                  key: "reveal",
                  label: t("fileActions.reveal"),
                  onSelect: revealFolder,
                  disabled: !collection.folder_path,
                },
                { key: "copy", label: t("knowledge.collection.copyPath"), onSelect: copyPath },
                {
                  key: "rename",
                  label: t("knowledge.rename.menu"),
                  onSelect: () => setRenaming(true),
                },
                {
                  key: "delete",
                  label: t("knowledge.deleteCollection.menu"),
                  onSelect: () => setDeleting(true),
                  destructive: true,
                  separated: true,
                },
              ]}
            />
          </>
        }
      />
      <KnowledgeRenameDialog collection={collection} open={renaming} onOpenChange={setRenaming} />
      <KnowledgeDeleteCollection
        collection={collection}
        open={deleting}
        onOpenChange={setDeleting}
      />

      <div className="min-h-0 flex-1 overflow-auto px-8 py-7">
        <div className="mx-auto flex max-w-[720px] flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <h1 className="font-mono text-lg font-semibold">{collection.name}</h1>
            {editing ? (
              <DescriptionEditor collection={collection} onDone={() => setEditing(false)} />
            ) : (
              <button
                type="button"
                title={t("knowledge.collection.clickToEdit")}
                onClick={() => setEditing(true)}
                className={
                  collection.description
                    ? "-mx-1.5 rounded-md px-1.5 py-0.5 text-left text-sm leading-[1.6] text-text hover:bg-surface-sunken"
                    : "-mx-1.5 rounded-md px-1.5 py-0.5 text-left text-sm text-text-subtle hover:bg-surface-sunken"
                }
              >
                {collection.description || t("knowledge.collection.noDescription")}
              </button>
            )}
          </div>
          <KnowledgeStatsLine collection={collection} />
          {empty ? (
            <p className="flex flex-wrap items-center gap-x-1 text-sm text-text-muted">
              {t("knowledge.collection.emptyLine")}
              {collection.folder_path ? (
                <button
                  type="button"
                  className="text-xs font-label text-accent-text hover:underline"
                  onClick={revealFolder}
                >
                  {t("fileActions.reveal")}
                </button>
              ) : null}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** The description as a textarea: blur or ⌘Enter saves, Esc cancels. An empty
 *  description is never saved — leaving it blank keeps the old one. */
function DescriptionEditor({
  collection,
  onDone,
}: {
  collection: CollectionOut;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const describe = useDescribeCollection(collection.uid);
  const [value, setValue] = useState(collection.description);
  // One decision per editing session: Esc must not be followed by a blur-save.
  const settled = useRef(false);
  const text = value.trim();

  const save = () => {
    if (settled.current || describe.isPending) return;
    if (!text || text === collection.description) {
      settled.current = true;
      onDone();
      return;
    }
    const previous = collection.description;
    describe.mutate(text, {
      onSuccess: () => {
        settled.current = true;
        onDone();
        toast.success(t("knowledge.collection.descriptionSaved"), {
          // Undo is the same describe mutation with the old text; a collection
          // that had no description has nothing to go back to.
          undo: previous
            ? () =>
                void describe
                  .mutateAsync(previous)
                  .catch(() => toast.error(t("knowledge.collection.descriptionUndoFailed")))
            : undefined,
        });
      },
    });
  };

  return (
    <div className="flex flex-col gap-2">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label={t("knowledge.collection.descriptionLabel")}
        autoFocus
        onBlur={save}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            save();
          } else if (e.key === "Escape") {
            e.preventDefault();
            settled.current = true;
            onDone();
          }
        }}
      />
      {describe.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, describe.error)}
        </p>
      ) : null}
    </div>
  );
}
