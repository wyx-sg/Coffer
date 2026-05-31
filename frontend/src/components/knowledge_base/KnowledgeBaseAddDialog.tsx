// frontend/src/components/knowledge_base/KnowledgeBaseAddDialog.tsx
// Modal "New knowledge base" dialog (mirrors SkillAddDialog). The search mode
// picks `keyword` (plain text, no embeddings — the default) or `semantic`
// (LlamaIndex vectors); the embedding-model field only shows for semantic.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createKnowledgeBase } from "@/kinds/knowledge_base/api";
import { translateApiError } from "@/lib/api/errors";

const DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5";

type SearchMode = "keyword" | "semantic";

export function KnowledgeBaseAddDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("keyword");
  const [embeddingModel, setEmbeddingModel] = useState(DEFAULT_EMBEDDING_MODEL);

  const reset = () => {
    setName("");
    setDescription("");
    setSearchMode("keyword");
    setEmbeddingModel(DEFAULT_EMBEDDING_MODEL);
  };

  const create = useMutation({
    mutationFn: () =>
      createKnowledgeBase({
        name,
        description: description.trim() || null,
        config: {
          search_mode: searchMode,
          embedding_model: embeddingModel,
          chunk_size: 512,
          chunk_overlap: 64,
          max_document_bytes: 25 * 1024 * 1024,
        },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      reset();
      onCreated();
      onOpenChange(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          create.reset();
          reset();
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("knowledgeBases.dialog.title")}</DialogTitle>
          <DialogDescription>{t("knowledgeBases.subtitle")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="kb-name">{t("knowledgeBases.dialog.name")}</Label>
            <Input
              id="kb-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              pattern="[a-zA-Z0-9_-]+"
              placeholder="e.g. design-notes"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="kb-description">{t("knowledgeBases.dialog.description")}</Label>
            <Input
              id="kb-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="kb-mode">{t("knowledgeBases.dialog.searchMode")}</Label>
            <select
              id="kb-mode"
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={searchMode}
              onChange={(e) => setSearchMode(e.target.value as SearchMode)}
            >
              <option value="keyword">{t("knowledgeBases.dialog.modeKeyword")}</option>
              <option value="semantic">{t("knowledgeBases.dialog.modeSemantic")}</option>
            </select>
            <p className="text-xs text-muted-foreground">
              {searchMode === "keyword"
                ? t("knowledgeBases.dialog.modeKeywordHint")
                : t("knowledgeBases.dialog.modeSemanticHint")}
            </p>
          </div>
          {searchMode === "semantic" ? (
            <div className="space-y-2">
              <Label htmlFor="kb-model">{t("knowledgeBases.dialog.embeddingModel")}</Label>
              <Input
                id="kb-model"
                value={embeddingModel}
                onChange={(e) => setEmbeddingModel(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {t("knowledgeBases.dialog.embeddingHint")}
              </p>
            </div>
          ) : null}
          {create.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, create.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? t("common.saving") : t("knowledgeBases.add")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
