// frontend/src/components/knowledge/KnowledgeDeleteCollection.tsx
//
// The collection overview's danger zone (boards 5.1.13, 5.1.19): Delete
// collection, behind a typed confirmation — it removes the folder, every
// document and every inbox item from disk. The delete is one change in the
// vault's history, so Recent changes lists it with Restore (spec knowledge
// "Restore a deleted collection or document from Recent changes"). A
// collection is one `knowledge` Resource, so it goes through the kind-agnostic
// resource delete like every other kind. The dialog closes only once the
// delete has landed, and a refusal stays in it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Trash2 } from "lucide-react";

import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useDeleteResource } from "@/lib/hooks/useResourceMutations";
import { KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";

export function KnowledgeDeleteCollection({ collection }: { collection: CollectionOut }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const del = useDeleteResource();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");

  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex min-h-[26px] items-center text-sm font-semibold">
        {t("knowledge.deleteCollection.zone")}
      </h3>
      <div className="flex min-h-14 items-center gap-6 rounded-lg border border-border bg-surface-raised px-4 py-2.5">
        <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
          <span className="text-sm font-medium">{t("knowledge.deleteCollection.confirm")}</span>
          <span className="text-xs leading-[1.45] text-text-subtle">
            {t("knowledge.deleteCollection.hint", { count: collection.document_count })}
          </span>
        </div>
        <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
          <Trash2 aria-hidden /> {t("knowledge.deleteCollection.button")}
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setTyped("");
            del.reset();
          }
        }}
        title={t("knowledge.deleteCollection.title", { name: collection.name })}
        description={t("knowledge.deleteCollection.body", {
          documents: collection.document_count,
          items: collection.pending_count,
        })}
        confirmLabel={
          del.isPending ? t("common.deleting") : t("knowledge.deleteCollection.confirm")
        }
        pending={del.isPending || typed !== collection.name}
        error={del.error}
        onConfirm={() =>
          del.mutate(
            { kind: "knowledge", uid: collection.uid },
            {
              onSuccess: () => {
                setOpen(false);
                navigate(KNOWLEDGE_ROOT);
              },
            },
          )
        }
      >
        <label className="block space-y-1.5 text-sm">
          <span className="text-text-muted">
            {t("knowledge.deleteCollection.typeToConfirm", { name: collection.name })}
          </span>
          <Input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            aria-label={t("knowledge.deleteCollection.typeToConfirm", { name: collection.name })}
            autoComplete="off"
          />
        </label>
      </ConfirmDialog>
    </section>
  );
}
