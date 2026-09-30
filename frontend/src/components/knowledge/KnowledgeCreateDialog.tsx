// frontend/src/components/knowledge/KnowledgeCreateDialog.tsx
// New collection: a name (its folder under ~/.coffer/knowledge/) and what
// belongs in it (the folder's README, which the coffer-guide skill carries to
// every agent). The hook toasts a failure; the dialog closes on success and
// opens the new collection.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

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
import { Textarea } from "@/components/ui/textarea";
import { useCreateCollection } from "@/lib/hooks/useKnowledge";
import { collectionPath } from "@/lib/knowledge/routes";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function KnowledgeCreateDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateCollection();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
    }
  }, [open]);

  const submit = () =>
    create.mutate(
      { name: name.trim(), description: description.trim() || null },
      {
        onSuccess: (created) => {
          onOpenChange(false);
          navigate(collectionPath(created.uid));
        },
      },
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("knowledge.create.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.create.body")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-collection-name" required>
              {t("knowledge.create.name")}
            </Label>
            <Input
              id="knowledge-collection-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="team-notes"
            />
            <p className="text-xs text-text-subtle">
              {t("knowledge.create.folder", { name: name.trim() || "…" })}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-collection-description">
              {t("knowledge.create.description")}
            </Label>
            <Textarea
              id="knowledge-collection-description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("knowledge.create.descriptionHint")}
            />
            <p className="text-xs text-text-subtle">{t("knowledge.create.everyAgent")}</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!name.trim() || create.isPending}>
            {t("knowledge.create.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
