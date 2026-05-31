// frontend/src/components/memory/MemoryStoreAddDialog.tsx
// Modal "New memory store" dialog (mirrors KnowledgeBaseAddDialog). The LLM
// provider chooses how mem0 extracts facts at write time: `none` (reads only),
// `ollama` (local), or `openai` (cloud — needs a keychain reference). The
// embedding model + per-memory cap use backend defaults (configurable later
// in Settings), keeping the create flow short.
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
import { createMemoryStore } from "@/kinds/memory/api";
import { translateApiError } from "@/lib/api/errors";

const DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5";
const DEFAULT_MAX_MEMORY_CHARS = 8192;

type Provider = "none" | "ollama" | "openai";

export function MemoryStoreAddDialog({
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
  const [llmProvider, setLlmProvider] = useState<Provider>("none");
  const [llmModel, setLlmModel] = useState("");
  const [llmEndpoint, setLlmEndpoint] = useState("");
  const [llmCredentialRef, setLlmCredentialRef] = useState("");

  const reset = () => {
    setName("");
    setDescription("");
    setLlmProvider("none");
    setLlmModel("");
    setLlmEndpoint("");
    setLlmCredentialRef("");
  };

  const create = useMutation({
    mutationFn: () =>
      createMemoryStore({
        name,
        description: description.trim() || null,
        config: {
          embedding_model: DEFAULT_EMBEDDING_MODEL,
          llm_provider: llmProvider,
          llm_model: llmModel.trim() || null,
          llm_endpoint: llmEndpoint.trim() || null,
          llm_credential_ref: llmCredentialRef.trim() || null,
          max_memory_chars: DEFAULT_MAX_MEMORY_CHARS,
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
          <DialogTitle>{t("memory.dialog.title")}</DialogTitle>
          <DialogDescription>{t("memory.subtitle")}</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="mem-name">{t("memory.dialog.name")}</Label>
            <Input
              id="mem-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              pattern="[a-zA-Z0-9_-]+"
              placeholder="e.g. coding-prefs"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mem-description">{t("memory.dialog.description")}</Label>
            <Input
              id="mem-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mem-llm-provider">{t("memory.dialog.llmProvider")}</Label>
            <select
              id="mem-llm-provider"
              className="block w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={llmProvider}
              onChange={(e) => setLlmProvider(e.target.value as Provider)}
            >
              <option value="none">{t("memory.dialog.providerNone")}</option>
              <option value="ollama">{t("memory.dialog.providerOllama")}</option>
              <option value="openai">{t("memory.dialog.providerOpenai")}</option>
            </select>
            <p className="text-xs text-muted-foreground">{t("memory.dialog.providerHint")}</p>
          </div>
          {llmProvider !== "none" ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="mem-llm-model">{t("memory.dialog.llmModel")}</Label>
                <Input
                  id="mem-llm-model"
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  placeholder={llmProvider === "ollama" ? "llama3.1" : "gpt-4o-mini"}
                  required
                />
              </div>
              {llmProvider === "ollama" ? (
                <div className="space-y-2">
                  <Label htmlFor="mem-llm-endpoint">{t("memory.dialog.llmEndpoint")}</Label>
                  <Input
                    id="mem-llm-endpoint"
                    value={llmEndpoint}
                    onChange={(e) => setLlmEndpoint(e.target.value)}
                    placeholder="http://localhost:11434"
                  />
                </div>
              ) : null}
              {llmProvider === "openai" ? (
                <div className="space-y-2">
                  <Label htmlFor="mem-llm-cred">{t("memory.dialog.llmCredential")}</Label>
                  <Input
                    id="mem-llm-cred"
                    value={llmCredentialRef}
                    onChange={(e) => setLlmCredentialRef(e.target.value)}
                    placeholder="e.g. openai-key (set via `coffer keychain`)"
                    required
                  />
                </div>
              ) : null}
            </>
          ) : null}
          {create.error ? (
            <p className="text-sm text-destructive">{translateApiError(t, create.error)}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? t("common.saving") : t("memory.add")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
