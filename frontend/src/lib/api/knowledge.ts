// frontend/src/lib/api/knowledge.ts
//
// The unified 知识 model (specs 006 FR-019 + 007 FR-017b, ADR-030): 知识 =
// 记忆 (notes) + 文档 (documents) × 全局 / 项目. This module owns the
// presentation-only shapes that fold the two underlying faces — memory stores
// (notes) and knowledge-base documents — into ONE scope-keyed list. The wire
// types and fetch helpers stay in `kinds/memory/api` and `kinds/knowledge_base/api`;
// here we only define the merged view types + the pure mapping helpers that the
// `useKnowledge` hook composes. Keeping the mapping pure makes it unit-testable
// without a network.

import {
  WORKSPACE_GLOBAL_PROJECT_ID,
  projectDirName,
  type FactOut,
  type MemoryStoreOut,
} from "@/kinds/memory/api";
import type { DocumentOut } from "@/kinds/knowledge_base/api";

export { WORKSPACE_GLOBAL_PROJECT_ID };

/** A note (a memory fact) or a document (a KB doc) — the two item shapes. */
export type KnowledgeItemType = "note" | "document";

/**
 * One scope on the primary axis: 全局 (global) or a project. The id is the
 * `project_id` both faces key on (the WORKSPACE_GLOBAL sentinel for global, or a
 * project ULID). `memoryStoreName` is the memory store that holds this scope's
 * notes (null when no store exists for the scope yet).
 */
export interface KnowledgeScope {
  id: string;
  kind: "global" | "project";
  /** Readable label: "全局" handled by the UI for global; project dir basename otherwise. */
  label: string;
  /** Absolute project root path (project scopes only) — shown as a secondary detail. */
  projectRoot: string | null;
  /** Memory store name backing this scope's notes (null if not provisioned). */
  memoryStoreName: string | null;
}

/**
 * A unified list row. A note and a document share the legible fields the list
 * renders (title, preview, scope, timestamps) and carry their origin so the
 * viewer + actions can route back to the right face. `ref` keys the row.
 */
export interface KnowledgeItem {
  ref: string;
  type: KnowledgeItemType;
  scopeId: string;
  title: string;
  /** A short preview for the description column (fact description or doc title). */
  preview: string;
  updatedAt: string;
  // Note-only origin. The fact body + on-disk paths ride along (facts are fully
  // loaded by listFacts) so the read-only viewer needs no second fetch.
  storeName?: string;
  factId?: string;
  actor?: string;
  noteBody?: string;
  noteType?: string | null;
  // Document-only origin. The markdown body is fetched lazily by the viewer
  // (listDocuments returns metadata only); the on-disk paths come from the list.
  kbName?: string;
  documentId?: string;
  locked?: boolean;
  sourceMode?: string;
  /** Set on trashed documents (the trash list only). */
  deletedAt?: string | null;
  // Absolute on-disk paths backing the read-only FileActions (open/reveal/copy).
  path?: string;
  folderPath?: string;
}

/**
 * Build the scope axis from the memory stores. Memory auto-provisions a global
 * store plus one per project, and each store carries the `project_id` + readable
 * `project_root` (FR-017a) the axis needs. The global scope is always present
 * (synthesized from the sentinel) even before its store row arrives, so the
 * landing surface never renders an empty axis.
 */
export function scopesFromStores(stores: MemoryStoreOut[]): KnowledgeScope[] {
  const byId = new Map<string, KnowledgeScope>();
  // Always offer the global scope first.
  byId.set(WORKSPACE_GLOBAL_PROJECT_ID, {
    id: WORKSPACE_GLOBAL_PROJECT_ID,
    kind: "global",
    label: "",
    projectRoot: null,
    memoryStoreName: null,
  });
  for (const s of stores) {
    const isGlobal = s.project_id === WORKSPACE_GLOBAL_PROJECT_ID;
    const existing = byId.get(s.project_id);
    if (existing) {
      existing.memoryStoreName = s.name;
      existing.projectRoot = s.project_root ?? existing.projectRoot;
      continue;
    }
    byId.set(s.project_id, {
      id: s.project_id,
      kind: isGlobal ? "global" : "project",
      label: projectDirName(s.project_root) ?? s.name,
      projectRoot: s.project_root ?? null,
      memoryStoreName: s.name,
    });
  }
  const all = [...byId.values()];
  const global = all.filter((s) => s.kind === "global");
  const projects = all
    .filter((s) => s.kind === "project")
    .sort((a, b) => a.label.localeCompare(b.label));
  return [...global, ...projects];
}

/** Map a memory fact to a unified note row. */
export function noteFromFact(storeName: string, scopeId: string, fact: FactOut): KnowledgeItem {
  return {
    ref: `note:${storeName}:${fact.id}`,
    type: "note",
    scopeId,
    title: fact.name || fact.text.slice(0, 60) || "(untitled)",
    preview: fact.description || fact.text.slice(0, 120),
    updatedAt: fact.updated_at,
    storeName,
    factId: fact.id,
    actor: fact.actor,
    noteBody: fact.text,
    noteType: fact.type ?? null,
    path: fact.path,
    folderPath: fact.folder_path,
  };
}

/** Map a KB document to a unified document row. */
export function documentFromDoc(kbName: string, doc: DocumentOut): KnowledgeItem {
  return {
    ref: `doc:${kbName}:${doc.id}`,
    type: "document",
    scopeId: doc.project_id,
    title: doc.title,
    preview: doc.description || "",
    updatedAt: doc.updated_at,
    kbName,
    documentId: doc.id,
    locked: doc.locked,
    sourceMode: doc.source_mode,
    deletedAt: doc.deleted_at ?? null,
    path: doc.path,
    folderPath: doc.folder_path,
  };
}
