// frontend/src/components/knowledge/KnowledgeDisconnectDialog.tsx
//
// Disconnect… from a linked folder's ⋯ menu: the agents stop seeing the folder
// and every file in it stays where it is. It asks first and says both halves.
// A linked folder is one `knowledge` Resource, so it goes through the
// kind-agnostic resource delete, whose hook leaves the folder alone.
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";

interface Props {
  collection: CollectionOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KnowledgeDisconnectDialog({ collection, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const navigate = useNavigate();
  const del = useDeleteResource();

  const confirm = () =>
    del.mutateAsync({ kind: "knowledge", uid: collection.uid }).then(() => {
      navigate(KNOWLEDGE_ROOT);
      toast.success(t("knowledge.disconnect.done", { name: collection.name }));
    });

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("knowledge.disconnect.title", { name: collection.name })}
      description={t("knowledge.disconnect.body", { path: collection.folder_path })}
      confirmLabel={t("knowledge.disconnect.confirm")}
      pendingLabel={t("knowledge.disconnect.pending")}
      errorTitle={t("knowledge.disconnect.failed", { name: collection.name })}
      error={del.error}
      onConfirm={confirm}
    />
  );
}
