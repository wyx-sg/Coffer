// frontend/src/components/knowledge/KnowledgeLinkedView.tsx
//
// A linked folder with no file open (spec knowledge "Link a folder the person
// keeps themselves"). Coffer only shares it with the agents, so the page shows
// what it is and nothing to manage: an "External" tag, its README's opening
// paragraph (not editable here: Coffer writes nothing into the folder), where
// it lives, how many notes it holds, its own rules file, and a line saying who
// manages it. No Tidy, To do, Contents or Change log. The ⋯ menu is Reveal in
// Finder · Open in Obsidian (only when installed) · Copy path · Rename… (a
// label only) · Disconnect…, which leaves every file where it is.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeDisconnectDialog } from "@/components/knowledge/KnowledgeDisconnectDialog";
import { KnowledgePaneBar } from "@/components/knowledge/KnowledgePaneBar";
import { KnowledgeRenameDialog } from "@/components/knowledge/KnowledgeRenameDialog";
import { Badge } from "@/components/ui/badge";
import { ActionMenu } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useFsActions } from "@/lib/fsActions";
import { useOpenInObsidian } from "@/lib/knowledge/obsidian";

interface Props {
  collection: CollectionOut;
}

export function KnowledgeLinkedView({ collection }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { reveal } = useFsActions();
  const [renaming, setRenaming] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const obsidian = useOpenInObsidian(collection.folder_path);

  const revealFolder = () =>
    void reveal(collection.folder_path).catch(() => toast.error(t("fileActions.revealFailed")));
  const copyPath = () =>
    void navigator.clipboard.writeText(collection.folder_path).then(
      () => toast.success(t("common.copied")),
      () => toast.error(t("knowledge.collection.copyFailed")),
    );

  const facts: [string, React.ReactNode][] = [
    [
      t("knowledge.linked.location"),
      <span key="path" className="flex min-w-0 flex-wrap items-center gap-x-2">
        <span className="break-all font-mono text-xs">{collection.folder_path}</span>
        <button
          type="button"
          className="text-xs font-label text-accent-text hover:underline"
          onClick={revealFolder}
        >
          {t("fileActions.reveal")}
        </button>
      </span>,
    ],
    [
      t("knowledge.linked.notes"),
      t("knowledge.linked.noteCount", { count: collection.note_count }),
    ],
    [
      t("knowledge.linked.rules"),
      collection.rules_file ? (
        <span className="font-mono text-xs">{collection.rules_file}</span>
      ) : (
        t("knowledge.linked.noRules")
      ),
    ],
    [t("knowledge.linked.managed"), t("knowledge.linked.managedBy")],
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <KnowledgePaneBar
        crumbs={[{ label: collection.name, mono: true }]}
        actions={
          <ActionMenu
            label={t("knowledge.collection.more", { name: collection.name })}
            actions={[
              { key: "reveal", label: t("fileActions.reveal"), onSelect: revealFolder },
              ...(obsidian ? [obsidian] : []),
              { key: "copy", label: t("knowledge.collection.copyPath"), onSelect: copyPath },
              {
                key: "rename",
                label: t("knowledge.rename.menu"),
                onSelect: () => setRenaming(true),
              },
              {
                key: "disconnect",
                label: t("knowledge.disconnect.menu"),
                onSelect: () => setDisconnecting(true),
                destructive: true,
                separated: true,
              },
            ]}
          />
        }
      />
      <KnowledgeRenameDialog collection={collection} open={renaming} onOpenChange={setRenaming} />
      <KnowledgeDisconnectDialog
        collection={collection}
        open={disconnecting}
        onOpenChange={setDisconnecting}
      />

      <div className="min-h-0 flex-1 overflow-auto px-8 py-7">
        <div className="mx-auto flex max-w-[720px] flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <h1 className="flex items-center gap-2 font-mono text-lg font-semibold">
              {collection.name}
              <Badge variant="secondary" className="font-sans">
                {t("knowledge.linked.tag")}
              </Badge>
            </h1>
            {collection.description ? (
              <p className="text-sm leading-[1.6] text-text">{collection.description}</p>
            ) : null}
          </div>
          <dl
            aria-label={t("knowledge.linked.facts")}
            className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-3 text-sm"
          >
            {facts.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-text-muted">{label}</dt>
                <dd className="min-w-0 text-text">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
