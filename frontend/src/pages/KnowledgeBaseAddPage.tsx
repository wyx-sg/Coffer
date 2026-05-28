// frontend/src/pages/KnowledgeBaseAddPage.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createKnowledgeBase } from "@/kinds/knowledge_base/api";

const DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5";

export function KnowledgeBaseAddPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState(DEFAULT_EMBEDDING_MODEL);
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () =>
      createKnowledgeBase({
        name,
        description: description.trim() || null,
        config: {
          embedding_model: embeddingModel,
          chunk_size: 512,
          chunk_overlap: 64,
          max_document_bytes: 25 * 1024 * 1024,
        },
      }),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      navigate(`/resources/knowledge_base/${data.name}`);
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
          <CardTitle>Add Knowledge Base</CardTitle>
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
              <Label htmlFor="kb-name">Name</Label>
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
              <Label htmlFor="kb-description">Description (optional)</Label>
              <Input
                id="kb-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="kb-model">Embedding model</Label>
              <Input
                id="kb-model"
                value={embeddingModel}
                onChange={(e) => setEmbeddingModel(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                A HuggingFace model id; default is suitable for English text.
              </p>
            </div>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? "Creating…" : "Create knowledge base"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
