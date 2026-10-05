// frontend/src/components/memory/MemoryViewActions.tsx — a memory's actions
// (spec memory "Show a partition's memories read-only"): Open in editor visible,
// and a ⋯ menu with Reveal in Finder and Delete…. Delete asks first; the dialog closes only on success, and
// the memory then sits in the Retired group as "Deleted by hand".
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ActionMenu } from "@/components/ui/menu";
import { useToast } from "@/components/ui/toast";
import { useFileActionItems } from "@/lib/fileActionItems";
import { useDeleteMemoryNote } from "@/lib/hooks/useMemory";

interface Props {
  uid: string;
  slug: string;
  title: string;
  filePath: string;
}

export function MemoryViewActions({ uid, slug, title, filePath }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const deleteNote = useDeleteMemoryNote(uid);
  const [openItem, revealItem] = useFileActionItems(filePath);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <>
      <Button variant="outline" onClick={openItem.onClick}>
        <ExternalLink aria-hidden /> {openItem.label}
      </Button>
      <ActionMenu
        label={t("memory.memories.more", { title })}
        actions={[
          { key: "reveal", label: revealItem.label, onSelect: revealItem.onClick },
          {
            key: "delete",
            label: t("memory.memories.deleteMenu"),
            destructive: true,
            separated: true,
            onSelect: () => setConfirmDelete(true),
          },
        ]}
      />
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={(open) => {
          if (!open) deleteNote.reset();
          setConfirmDelete(open);
        }}
        title={t("memory.memories.deleteTitle", { title })}
        description={t("memory.memories.deleteBody")}
        confirmLabel={t("memory.memories.deleteConfirm")}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDelete", { name: title })}
        variant="destructive"
        pending={deleteNote.isPending}
        error={deleteNote.error}
        onConfirm={() =>
          deleteNote.mutate(slug, {
            onSuccess: () => {
              setConfirmDelete(false);
              toast.success(t("memory.memories.deleted", { title }));
            },
          })
        }
      />
    </>
  );
}
