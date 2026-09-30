// frontend/src/components/knowledge/KnowledgeAddDocumentDialog.tsx
//
// Add a document (添加文档): a title and a body, submitted as an ITEM into the
// chosen collection's Inbox with the web UI's actor, `user` (spec knowledge
// "Present a collection as one tree in the web UI", "Submit material through
// coffer__write"). It is curated into the right document like any other item —
// the person never picks a file; curation does. With Coffer's model not set it
// is written as a document as it is, and the dialog says which happened.
//
// An item must describe itself (the daemon requires a description), so the
// dialog takes the body's first sentence, or the title when there is no body.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeCollectionSelect } from "@/components/knowledge/KnowledgeCollectionSelect";
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
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { CollectionOut } from "@/lib/api/knowledge";
import { useSubmitMaterial } from "@/lib/hooks/useKnowledge";
import { describeItem } from "@/lib/knowledge/text";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collections: CollectionOut[];
  /** The collection on screen, preselected; the first one otherwise. */
  initial: string | null;
  modelSet: boolean | undefined;
}

export function KnowledgeAddDocumentDialog(props: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const submit = useSubmitMaterial();
  const [collection, setCollection] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");

  useEffect(() => {
    if (props.open) {
      setCollection(props.initial ?? props.collections[0]?.name ?? "");
      setTitle("");
      setBody("");
      submit.reset();
    }
    // Reset only when the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.open]);

  const onSubmit = () =>
    submit.mutate(
      {
        collection,
        title: title.trim(),
        description: describeItem(title.trim(), body),
        body,
      },
      {
        onSuccess: (out) => {
          toast.success(
            out.status === "pending"
              ? t("knowledge.add.pending", { collection: out.collection })
              : t("knowledge.add.written", { path: out.path ?? out.title }),
          );
          props.onOpenChange(false);
        },
      },
    );

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("knowledge.add.title")}</DialogTitle>
          <DialogDescription>
            {props.modelSet === false ? t("knowledge.add.hintNoModel") : t("knowledge.add.hint")}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-add-collection" required>
              {t("knowledge.add.collection")}
            </Label>
            <KnowledgeCollectionSelect
              id="knowledge-add-collection"
              collections={props.collections}
              value={collection}
              onChange={setCollection}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-add-title" required>
              {t("knowledge.add.titleField")}
            </Label>
            <Input
              id="knowledge-add-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="knowledge-add-body" required>
              {t("knowledge.add.body")}
            </Label>
            <Textarea
              id="knowledge-add-body"
              rows={8}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>
          {submit.error ? (
            <p role="alert" className="text-sm text-danger">
              {translateApiError(t, submit.error)}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => props.onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={onSubmit}
            disabled={!collection || !title.trim() || !body.trim() || submit.isPending}
          >
            {props.modelSet === false
              ? t("knowledge.add.submitNoModel")
              : t("knowledge.add.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
