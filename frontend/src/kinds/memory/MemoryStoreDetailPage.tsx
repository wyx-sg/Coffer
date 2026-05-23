// frontend/src/kinds/memory/MemoryStoreDetailPage.tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  addMemory,
  clearMemories,
  deleteMemory,
  getMemoryStoreMetrics,
  listMemories,
  searchMemories,
  updateMemory,
  type MemoryOut,
  type MemorySearchHit,
} from "./api";

export function MemoryStoreDetailPage() {
  const params = useParams<{ name: string }>();
  const store = params.name ?? "";
  const qc = useQueryClient();
  const [newText, setNewText] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<MemorySearchHit[] | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const memQuery = useQuery({
    queryKey: ["memories", store],
    queryFn: () => listMemories(store, 100, 0),
    enabled: Boolean(store),
  });

  const metricsQuery = useQuery({
    queryKey: ["memory-metrics", store],
    queryFn: () => getMemoryStoreMetrics(store),
    enabled: Boolean(store),
  });

  const add = useMutation({
    mutationFn: () => addMemory(store, newText.trim()),
    onSuccess: () => {
      setNewText("");
      void qc.invalidateQueries({ queryKey: ["memories", store] });
      void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
    },
  });

  const del = useMutation({
    mutationFn: (id: string) => deleteMemory(store, id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memories", store] });
      void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
    },
  });

  const upd = useMutation({
    mutationFn: (input: { id: string; text: string }) => updateMemory(store, input.id, input.text),
    onSuccess: () => {
      setEditingId(null);
      setEditText("");
      void qc.invalidateQueries({ queryKey: ["memories", store] });
    },
  });

  const search = useMutation({
    mutationFn: () => searchMemories(store, query, 5),
    onSuccess: (data) => setHits(data),
  });

  const clear = useMutation({
    mutationFn: () => clearMemories(store),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["memories", store] });
      void qc.invalidateQueries({ queryKey: ["memory-metrics", store] });
    },
  });

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">{store}</h1>
        {metricsQuery.data ? (
          <p className="text-sm text-muted-foreground">
            {metricsQuery.data.memory_count} memories · {metricsQuery.data.disk_bytes} bytes
          </p>
        ) : null}
      </header>

      <section className="space-y-2">
        <div className="flex gap-2">
          <Input
            placeholder="Search memories…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query.trim()) search.mutate();
            }}
          />
          <Button onClick={() => search.mutate()} disabled={!query.trim() || search.isPending}>
            Search
          </Button>
        </div>
        {hits && hits.length > 0 ? (
          <ul className="space-y-2 text-sm">
            {hits.map((h, i) => (
              <li key={h.id} className="rounded border p-2">
                <div className="font-medium">
                  {i + 1}.{" "}
                  <span className="text-xs text-muted-foreground">score={h.score.toFixed(3)}</span>
                </div>
                <div>{h.text}</div>
              </li>
            ))}
          </ul>
        ) : hits ? (
          <p className="text-sm text-muted-foreground">No matches.</p>
        ) : null}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium">Memories</h2>
          <Button
            variant="destructive"
            onClick={() => {
              if (window.confirm(`Clear all memories in ${store}? This cannot be undone.`)) {
                clear.mutate();
              }
            }}
            disabled={clear.isPending}
          >
            Clear all
          </Button>
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="Add a new memory…"
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newText.trim()) add.mutate();
            }}
          />
          <Button onClick={() => add.mutate()} disabled={!newText.trim() || add.isPending}>
            Add
          </Button>
        </div>
        {memQuery.data ? (
          <ul className="divide-y rounded border">
            {memQuery.data.memories.map((m: MemoryOut) => (
              <li key={m.id} className="flex items-start justify-between gap-2 p-3">
                <div className="min-w-0 flex-1">
                  <div className="font-mono text-xs text-muted-foreground">
                    {m.id} · {m.actor}
                  </div>
                  {editingId === m.id ? (
                    <div className="mt-1 flex gap-2">
                      <Input value={editText} onChange={(e) => setEditText(e.target.value)} />
                      <Button
                        size="sm"
                        onClick={() => upd.mutate({ id: m.id, text: editText })}
                        disabled={!editText.trim() || upd.isPending}
                      >
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingId(null);
                          setEditText("");
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <div className="text-sm break-words">{m.text}</div>
                  )}
                </div>
                {editingId === m.id ? null : (
                  <div className="flex shrink-0 gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(m.id);
                        setEditText(m.text);
                      }}
                    >
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => del.mutate(m.id)}>
                      Delete
                    </Button>
                  </div>
                )}
              </li>
            ))}
            {memQuery.data.memories.length === 0 ? (
              <li className="p-3 text-sm text-muted-foreground">No memories yet.</li>
            ) : null}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
