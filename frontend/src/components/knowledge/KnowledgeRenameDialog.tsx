// frontend/src/components/knowledge/KnowledgeRenameDialog.tsx
// Rename… from a collection's ⋯ menu (board 5.1.31): one name field, the
// folder it becomes, Cancel / Rename. The collection's folder moves with the
// name (spec knowledge "Name a collection by its folder and edit its
// description in place"). The page address carries the uid, so it stays put.
// A refusal — the name taken, or not a valid folder name — is said under the
// field and the dialog stays open; it closes only on success.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useRenameCollection } from "@/lib/hooks/useKnowledge";

interface Props {
  collection: CollectionOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KnowledgeRenameDialog({ collection, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const rename = useRenameCollection();
  const [name, setName] = useState(collection.name);
  const { reset } = rename;

  useEffect(() => {
    if (open) {
      setName(collection.name);
      reset();
    }
  }, [open, collection.name, reset]);

  const next = name.trim();
  const submit = () =>
    rename.mutate(
      { uid: collection.uid, name: next },
      {
        onSuccess: () => {
          onOpenChange(false);
          toast.success(t("knowledge.rename.renamed", { name: next }));
        },
      },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("knowledge.rename.title", { name: collection.name })}</DialogTitle>
          <DialogDescription>{t("knowledge.rename.body")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (next && next !== collection.name && !rename.isPending) submit();
          }}
        >
          <Label htmlFor="knowledge-rename-name" required>
            {t("knowledge.create.name")}
          </Label>
          <Input
            id="knowledge-rename-name"
            value={name}
            autoFocus
            aria-invalid={rename.error ? true : undefined}
            onChange={(e) => setName(e.target.value)}
          />
          <p className="text-xs text-text-subtle">
            {t("knowledge.create.folder", { name: next || "…" })}
          </p>
          {rename.error ? (
            <p role="alert" className="text-xs text-danger">
              {translateApiError(t, rename.error)}
            </p>
          ) : null}
        </form>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={submit}
            disabled={!next || next === collection.name || rename.isPending}
          >
            {t("knowledge.rename.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
