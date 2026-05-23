// frontend/src/pages/MemoryStoreAddPage.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createMemoryStore } from "@/kinds/memory/api";

type Provider = "none" | "ollama" | "openai";

// CODE26-035: surface ``embedding_model`` and ``max_memory_chars`` as form
// fields rather than hardcoding them. Defaults match the backend's
// :class:`MemoryStoreConfig` defaults (see
// ``backend/coffer/domain/memory/config.py``) so users who don't customise
// these still get the documented values.
const DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5";
const DEFAULT_MAX_MEMORY_CHARS = 8192;

export function MemoryStoreAddPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState(DEFAULT_EMBEDDING_MODEL);
  const [maxMemoryChars, setMaxMemoryChars] = useState<number>(DEFAULT_MAX_MEMORY_CHARS);
  const [llmProvider, setLlmProvider] = useState<Provider>("none");
  const [llmModel, setLlmModel] = useState("");
  const [llmEndpoint, setLlmEndpoint] = useState("");
  const [llmCredentialRef, setLlmCredentialRef] = useState("");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      createMemoryStore({
        name,
        description: description.trim() || null,
        config: {
          embedding_model: embeddingModel.trim() || DEFAULT_EMBEDDING_MODEL,
          llm_provider: llmProvider,
          llm_model: llmModel.trim() || null,
          llm_endpoint: llmEndpoint.trim() || null,
          llm_credential_ref: llmCredentialRef.trim() || null,
          max_memory_chars: maxMemoryChars,
        },
      }),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      navigate(`/resources/memory/${data.name}`);
    },
    onError: (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
  });

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Button variant="ghost" size="sm" onClick={() => navigate("/resources")}>
        <ArrowLeft className="mr-2 size-4" /> Back
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>Add Memory Store</CardTitle>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="mb-4 rounded-md border border-destructive bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          ) : null}
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              setError(null);
              create.mutate();
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="mem-name">Name</Label>
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
              <Label htmlFor="mem-description">Description (optional)</Label>
              <Input
                id="mem-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mem-embedding-model">Embedding model</Label>
              <Input
                id="mem-embedding-model"
                value={embeddingModel}
                onChange={(e) => setEmbeddingModel(e.target.value)}
                placeholder={DEFAULT_EMBEDDING_MODEL}
              />
              <p className="text-xs text-muted-foreground">
                Immutable after creation. Default works for English on consumer hardware.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mem-max-chars">Max memory chars</Label>
              <Input
                id="mem-max-chars"
                type="number"
                min={64}
                max={32768}
                value={maxMemoryChars}
                onChange={(e) =>
                  setMaxMemoryChars(
                    Math.max(
                      64,
                      Math.min(32768, parseInt(e.target.value, 10) || DEFAULT_MAX_MEMORY_CHARS),
                    ),
                  )
                }
              />
              <p className="text-xs text-muted-foreground">
                Per-memory character cap. Range: 64-32768. Default: {DEFAULT_MAX_MEMORY_CHARS}.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mem-llm-provider">LLM Provider</Label>
              <select
                id="mem-llm-provider"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm"
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value as Provider)}
              >
                <option value="none">none (read-only writes disabled)</option>
                <option value="ollama">ollama (local)</option>
                <option value="openai">openai (cloud)</option>
              </select>
              <p className="text-xs text-muted-foreground">
                mem0 requires an LLM at write time to extract facts; reads work without one.
              </p>
            </div>
            {llmProvider !== "none" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="mem-llm-model">LLM Model</Label>
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
                    <Label htmlFor="mem-llm-endpoint">Ollama endpoint (optional)</Label>
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
                    <Label htmlFor="mem-llm-cred">Keychain reference</Label>
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
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? "Creating…" : "Create memory store"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
