// frontend/src/components/knowledge/KnowledgeCreateDialog.tsx
// Creating a collection asks two things and nothing else: a name, and a
// sentence saying what it is for. The description becomes the folder's
// `README.md`, which is where the catalogue reads it back from — so it is the
// line an agent sees when deciding whether to look inside (FR-013).
//
// There is no question about retrieval or vectors here. Which index a
// collection carries is not a question, because it carries none.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import { useCreateCollection } from "@/kinds/knowledge/useKnowledge";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

export function KnowledgeCreateDialog({ open, onOpenChange, onCreated }: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const create = useCreateCollection();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const submit = () => {
    create.mutate(
      { name: name.trim(), description: description.trim() || null },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          onOpenChange(false);
          onCreated?.();
        },
        onError: (e) => toast.error(translateApiError(t, e)),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("knowledge.create.title")}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-collection-name">{t("knowledge.create.name")}</Label>
            <Input
              id="knowledge-collection-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="shopee"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-collection-description">
              {t("knowledge.create.description")}
            </Label>
            <Input
              id="knowledge-collection-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("knowledge.create.descriptionHint")}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!name.trim() || create.isPending}>
            {t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
