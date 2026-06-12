// frontend/src/components/knowledge_base/KnowledgeBaseAddDialog.tsx
// Modal "New knowledge base" dialog. Keyword + grep are always on; a toggle
// opts into vector retrieval (the embedding model is GLOBAL — Settings →
// Embedding). New KBs seed their chunking from the global default (overridable
// later in the KB's own settings).
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
import { Switch } from "@/components/ui/switch";
import { createKnowledgeBase, type RetrievalMode } from "@/kinds/knowledge_base/api";
import { useEmbeddingConfig } from "@/lib/hooks/useEmbeddingConfig";
import { translateApiError } from "@/lib/api/errors";

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
  const { data: globalCfg } = useEmbeddingConfig();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [vectorEnabled, setVectorEnabled] = useState(false);

  const reset = () => {
    setName("");
    setDescription("");
    setVectorEnabled(false);
  };

  const create = useMutation({
    mutationFn: () => {
      const enabledModes: RetrievalMode[] = vectorEnabled
        ? ["keyword", "grep", "vector"]
        : ["keyword", "grep"];
      return createKnowledgeBase({
        name,
        description: description.trim() || null,
        config: {
          enabled_modes: enabledModes,
          default_mode: "keyword",
          // Seed chunking from the global default (overridable per-KB later).
          chunk_size: globalCfg?.default_chunk_size ?? 512,
          chunk_overlap: globalCfg?.default_chunk_overlap ?? 64,
          // Embedding is global (Settings → Embedding); the KB carries none.
          embedding: null,
        },
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-bases"] });
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
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="kb-vector">{t("knowledgeBases.dialog.vector")}</Label>
              <p className="text-xs text-muted-foreground">
                {t("knowledgeBases.settings.vectorHint")}
              </p>
            </div>
            <Switch id="kb-vector" checked={vectorEnabled} onCheckedChange={setVectorEnabled} />
          </div>
          {create.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, create.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              {create.isPending ? t("common.saving") : t("knowledgeBases.add")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
