// frontend/src/components/knowledge_base/KnowledgeBaseAddDialog.tsx
// Modal "New knowledge base" dialog (mirrors SkillAddDialog). Retrieval modes
// (keyword/grep are on by default; vector is opt-in) drive whether the
// embedding config block is shown: vector needs an embedding provider/model
// (+ optional base_url / keychain credential reference).
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
import { translateApiError } from "@/lib/api/errors";

const DEFAULT_PROVIDER = "local";
const DEFAULT_MODEL = "bge-m3";
const DEFAULT_DIMENSIONS = 1024;

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
  const [vectorEnabled, setVectorEnabled] = useState(false);
  const [provider, setProvider] = useState(DEFAULT_PROVIDER);
  const [model, setModel] = useState(DEFAULT_MODEL);
  const [baseUrl, setBaseUrl] = useState("");
  const [credentialRef, setCredentialRef] = useState("");
  const [dimensions, setDimensions] = useState(DEFAULT_DIMENSIONS);

  const reset = () => {
    setName("");
    setDescription("");
    setVectorEnabled(false);
    setProvider(DEFAULT_PROVIDER);
    setModel(DEFAULT_MODEL);
    setBaseUrl("");
    setCredentialRef("");
    setDimensions(DEFAULT_DIMENSIONS);
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
          embedding: vectorEnabled
            ? {
                provider,
                model,
                base_url: baseUrl.trim() || null,
                credential_ref: credentialRef.trim() || null,
                dimensions,
              }
            : null,
        },
      });
    },
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
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="kb-vector">{t("knowledgeBases.dialog.vector")}</Label>
              <p className="text-xs text-muted-foreground">
                {t("knowledgeBases.dialog.vectorHint")}
              </p>
            </div>
            <Switch id="kb-vector" checked={vectorEnabled} onCheckedChange={setVectorEnabled} />
          </div>
          {vectorEnabled ? (
            <div className="space-y-3 rounded-md border p-3">
              <div className="space-y-2">
                <Label htmlFor="kb-provider">{t("knowledgeBases.dialog.provider")}</Label>
                <Input
                  id="kb-provider"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  placeholder="local | openai | voyage | …"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-model">{t("knowledgeBases.dialog.embeddingModel")}</Label>
                <Input
                  id="kb-model"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-dimensions">{t("knowledgeBases.dialog.dimensions")}</Label>
                <Input
                  id="kb-dimensions"
                  type="number"
                  min={1}
                  value={dimensions}
                  onChange={(e) => setDimensions(Number(e.target.value) || DEFAULT_DIMENSIONS)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-base-url">{t("knowledgeBases.dialog.baseUrl")}</Label>
                <Input
                  id="kb-base-url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://… (optional, OpenAI-compatible)"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="kb-cred">{t("knowledgeBases.dialog.credential")}</Label>
                <Input
                  id="kb-cred"
                  value={credentialRef}
                  onChange={(e) => setCredentialRef(e.target.value)}
                  placeholder="keychain reference (optional)"
                />
              </div>
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
