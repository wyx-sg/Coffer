// frontend/src/lib/api/knowledge.test.ts
// The pure mappers that fold the two faces (memory facts + KB documents) into
// the unified scope-keyed model. No network — just shape transforms.
import { describe, expect, test } from "vitest";

import {
  WORKSPACE_GLOBAL_PROJECT_ID,
  documentFromDoc,
  noteFromFact,
  scopesFromStores,
} from "./knowledge";
import type { FactOut, MemoryStoreOut } from "@/kinds/memory/api";
import type { DocumentOut } from "@/kinds/knowledge_base/api";

const PROJECT_ULID = "01J2PROJECTULID0000000000";

function store(overrides: Partial<MemoryStoreOut>): MemoryStoreOut {
  return {
    ref: "memory:x",
    kind: "memory",
    name: "x",
    scope: "global",
    project_id: WORKSPACE_GLOBAL_PROJECT_ID,
    project_root: null,
    description: null,
    config: {
      retrieval_modes: ["keyword"],
      default_mode: "keyword",
      embedding_dimensions: 768,
      max_fact_chars: 8192,
    },
    enabled: true,
    created_at: "t",
    updated_at: "t",
    ...overrides,
  };
}

describe("scopesFromStores", () => {
  test("always offers a global scope, even with no stores", () => {
    const scopes = scopesFromStores([]);
    expect(scopes).toHaveLength(1);
    expect(scopes[0].kind).toBe("global");
    expect(scopes[0].id).toBe(WORKSPACE_GLOBAL_PROJECT_ID);
  });

  test("derives a project scope with a readable label from project_root", () => {
    const scopes = scopesFromStores([
      store({
        name: "project-abc",
        scope: "project",
        project_id: PROJECT_ULID,
        project_root: "/Users/me/code/coffer",
      }),
    ]);
    // Global first, then the project (sorted by label).
    expect(scopes.map((s) => s.kind)).toEqual(["global", "project"]);
    const project = scopes[1];
    expect(project.id).toBe(PROJECT_ULID);
    expect(project.label).toBe("coffer");
    expect(project.projectRoot).toBe("/Users/me/code/coffer");
    expect(project.memoryStoreName).toBe("project-abc");
  });

  test("binds the global store name to the synthesized global scope", () => {
    const scopes = scopesFromStores([
      store({ name: "global", project_id: WORKSPACE_GLOBAL_PROJECT_ID }),
    ]);
    expect(scopes[0].memoryStoreName).toBe("global");
  });

  test("sorts projects by label", () => {
    const scopes = scopesFromStores([
      store({ name: "p-z", scope: "project", project_id: "Z", project_root: "/x/zebra" }),
      store({ name: "p-a", scope: "project", project_id: "A", project_root: "/x/apple" }),
    ]);
    expect(scopes.slice(1).map((s) => s.label)).toEqual(["apple", "zebra"]);
  });
});

describe("noteFromFact", () => {
  const fact: FactOut = {
    id: "f1",
    store_name: "global",
    scope: "global",
    name: "Likes tea",
    description: "a preference",
    text: "The user likes green tea.",
    type: "preference",
    actor: "agent",
    path: "/p/f1.md",
    folder_path: "/p",
    created_at: "t",
    updated_at: "2026-06-19T00:00:00Z",
  };

  test("maps a fact to a note item carrying body + paths", () => {
    const item = noteFromFact("global", WORKSPACE_GLOBAL_PROJECT_ID, fact);
    expect(item.type).toBe("note");
    expect(item.ref).toBe("note:global:f1");
    expect(item.title).toBe("Likes tea");
    expect(item.preview).toBe("a preference");
    expect(item.noteBody).toBe("The user likes green tea.");
    expect(item.path).toBe("/p/f1.md");
    expect(item.scopeId).toBe(WORKSPACE_GLOBAL_PROJECT_ID);
  });

  test("falls back to the body text for an unnamed fact's title", () => {
    const item = noteFromFact("global", WORKSPACE_GLOBAL_PROJECT_ID, { ...fact, name: "" });
    expect(item.title).toBe("The user likes green tea.");
  });
});

describe("documentFromDoc", () => {
  const doc: DocumentOut = {
    id: "d1",
    kind: "knowledge_base",
    resource_name: "designs",
    title: "ADR-001.md",
    description: null,
    source_mode: "converted",
    content_sha256: "abc",
    locked: true,
    project_id: PROJECT_ULID,
    deleted_at: null,
    metadata: {},
    path: "/k/d1.md",
    folder_path: "/k",
    created_at: "t",
    updated_at: "2026-06-18T00:00:00Z",
  };

  test("maps a document to a document item with scope + lock + paths", () => {
    const item = documentFromDoc("designs", doc);
    expect(item.type).toBe("document");
    expect(item.ref).toBe("doc:designs:d1");
    expect(item.kbName).toBe("designs");
    expect(item.documentId).toBe("d1");
    expect(item.scopeId).toBe(PROJECT_ULID);
    expect(item.locked).toBe(true);
    expect(item.path).toBe("/k/d1.md");
    expect(item.deletedAt).toBeNull();
  });

  test("surfaces deleted_at for a trashed document", () => {
    const item = documentFromDoc("designs", { ...doc, deleted_at: "2026-06-19T01:00:00Z" });
    expect(item.deletedAt).toBe("2026-06-19T01:00:00Z");
  });
});
