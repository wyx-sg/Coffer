// frontend/src/components/knowledge/KnowledgeDeleteCollection.tsx
//
// The collection overview's danger zone: Delete collection, behind a typed
// confirmation — it removes the folder, every document and every inbox item
// from disk. A collection is one `knowledge` Resource, so it goes through the
// kind-agnostic resource delete like every other kind. The dialog closes only
// once the delete has landed, and a refusal stays in it.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

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
    <section className="space-y-2 rounded-xl border border-border-subtle p-4">
      <h3 className="text-sm font-semibold">{t("knowledge.deleteCollection.zone")}</h3>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text-muted">
          {t("knowledge.deleteCollection.hint", { count: collection.document_count })}
        </p>
        <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
          {t("knowledge.deleteCollection.button")}
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
