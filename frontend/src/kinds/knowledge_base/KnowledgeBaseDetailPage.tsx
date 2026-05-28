// frontend/src/kinds/knowledge_base/KnowledgeBaseDetailPage.tsx
import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  deleteDocument,
  getKnowledgeBaseMetrics,
  ingestDocument,
  listDocuments,
  searchKnowledgeBase,
  type DocumentOut,
  type SearchHit,
} from "./api";

export function KnowledgeBaseDetailPage() {
  const params = useParams<{ name: string }>();
  const name = params.name ?? "";
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);

  const docsQuery = useQuery({
    queryKey: ["kb-documents", name],
    queryFn: () => listDocuments(name, 50, 0),
    enabled: Boolean(name),
  });

  const metricsQuery = useQuery({
    queryKey: ["kb-metrics", name],
    queryFn: () => getKnowledgeBaseMetrics(name),
    enabled: Boolean(name),
  });

  const ingest = useMutation({
    mutationFn: (file: File) => ingestDocument(name, file, false),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["kb-documents", name] });
      void qc.invalidateQueries({ queryKey: ["kb-metrics", name] });
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => deleteDocument(name, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["kb-documents", name] });
      void qc.invalidateQueries({ queryKey: ["kb-metrics", name] });
    },
  });

  const search = useMutation({
    mutationFn: () => searchKnowledgeBase(name, query, 5),
    onSuccess: (data) => setHits(data),
  });

  const handlePickFile = () => fileInputRef.current?.click();
  const handleFileChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const f = e.target.files?.[0];
    if (f) ingest.mutate(f);
    e.target.value = "";
  };

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{name}</h1>
        {metricsQuery.data ? (
          <p className="text-sm text-muted-foreground">
            {metricsQuery.data.document_count} documents · {metricsQuery.data.disk_bytes} bytes on
            disk
          </p>
        ) : null}
      </header>

      <section className="space-y-2">
        <div className="flex gap-2">
          <Input
            placeholder="Search this knowledge base…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query.trim()) {
                search.mutate();
              }
            }}
          />
          <Button onClick={() => search.mutate()} disabled={!query.trim() || search.isPending}>
            Search
          </Button>
        </div>
        {hits && hits.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {hits.map((h, i) => (
              <li key={`${h.document_id}:${h.position}`} className="rounded border p-2">
                <div className="font-medium">
                  {i + 1}. {h.filename}{" "}
                  <span className="text-xs text-muted-foreground">score={h.score.toFixed(3)}</span>
                </div>
                <div className="line-clamp-3 text-muted-foreground">{h.text}</div>
              </li>
            ))}
          </ul>
        ) : hits ? (
          <p className="text-sm text-muted-foreground">No matches.</p>
        ) : null}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Documents</h2>
          <Button onClick={handlePickFile} disabled={ingest.isPending}>
            Upload
          </Button>
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileChange} />
        </div>
        {docsQuery.data ? (
          <ul className="divide-y rounded border">
            {docsQuery.data.documents.map((d: DocumentOut) => (
              <li key={d.id} className="flex items-center justify-between p-3">
                <div>
                  <div className="font-mono text-xs text-muted-foreground">{d.id}</div>
                  <div className="text-sm">{d.filename}</div>
                  <div className="text-xs text-muted-foreground">
                    {d.size_bytes} bytes · {d.chunk_count} chunks
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => del.mutate(d.id)}
                  disabled={del.isPending}
                >
                  Delete
                </Button>
              </li>
            ))}
            {docsQuery.data.documents.length === 0 ? (
              <li className="p-3 text-sm text-muted-foreground">
                No documents yet. Upload a file to populate this knowledge base.
              </li>
            ) : null}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
