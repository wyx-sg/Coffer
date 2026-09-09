// frontend/src/components/knowledge/KnowledgeAddDialog.tsx
// Modal "New collection" dialog. This only ever creates a NAMED collection:
// `global` and `project-<ULID>` auto-provision on first use and the backend
// rejects them with 422, so the name field refuses those shapes up front.
//
// Keyword + grep are always on; a toggle opts into vector retrieval (the
// embedding model is GLOBAL — Settings → Embedding — never per scope). New
// collections seed their chunking from the global default (overridable later in
// the scope's own settings).
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
import { createScope, type RetrievalMode } from "@/kinds/knowledge/api";
import { scopeNameSchema } from "@/kinds/knowledge/schema";
import { useEmbeddingConfig } from "@/lib/hooks/useEmbeddingConfig";
import { translateApiError } from "@/lib/api/errors";

export function KnowledgeAddDialog({
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

  // Reject the auto-provisioned names client-side so the user gets the reason
  // in place rather than a 422 after submit.
  const nameCheck = name.trim() ? scopeNameSchema.safeParse(name.trim()) : null;
  const nameError = nameCheck && !nameCheck.success ? nameCheck.error.issues[0].message : null;

  const reset = () => {
    setName("");
    setDescription("");
    setVectorEnabled(false);
  };

  const create = useMutation({
    mutationFn: () => {
      const retrievalModes: RetrievalMode[] = vectorEnabled
        ? ["keyword", "grep", "vector"]
        : ["keyword", "grep"];
      return createScope({
        name: name.trim(),
        description: description.trim() || null,
        config: {
          retrieval_modes: retrievalModes,
          // Seed chunking from the global default (overridable per-scope later).
          chunk_size: globalCfg?.default_chunk_size ?? 512,
          chunk_overlap: globalCfg?.default_chunk_overlap ?? 64,
        },
      });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["knowledge-scopes"] });
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
          <DialogTitle>{t("knowledge.dialog.title")}</DialogTitle>
          <DialogDescription>{t("knowledge.dialog.description")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!nameError) create.mutate();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="knowledge-name">{t("knowledge.dialog.name")}</Label>
            <Input
              id="knowledge-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              pattern="[a-zA-Z0-9_-]+"
              placeholder="e.g. design-notes"
            />
            <p className="text-xs text-muted-foreground">{t("knowledge.dialog.nameHint")}</p>
            {nameError ? <p className="text-sm text-destructive">{nameError}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="knowledge-description">{t("knowledge.dialog.descriptionField")}</Label>
            <Input
              id="knowledge-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="knowledge-vector">{t("knowledge.dialog.vector")}</Label>
              <p className="text-xs text-muted-foreground">{t("knowledge.settings.vectorHint")}</p>
            </div>
            <Switch
              id="knowledge-vector"
              checked={vectorEnabled}
              onCheckedChange={setVectorEnabled}
            />
          </div>
          {create.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, create.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending || !name.trim() || Boolean(nameError)}>
              {create.isPending ? t("common.saving") : t("knowledge.add")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
