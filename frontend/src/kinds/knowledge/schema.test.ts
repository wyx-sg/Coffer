// frontend/src/kinds/knowledge/schema.test.ts
//
// Pin the Zod schemas in `schema.ts`: the merged per-scope config, the
// "new collection" form and the add-entry form. A regression here yields silent
// drift between the frontend forms and the backend's KnowledgeConfig.
//
// There are no embedding fields on either side of the merge any more —
// embedding is installation-wide, and a scope opts into vector search purely by
// listing the mode.

import { describe, expect, test } from "vitest";
import { addEntryFormSchema, addScopeFormSchema, knowledgeConfigSchema } from "./schema";

describe("knowledgeConfigSchema", () => {
  test("accepts an empty config and fills defaults", () => {
    const parsed = knowledgeConfigSchema.parse({});
    expect(parsed.retrieval_modes).toEqual(["grep", "keyword"]);
    expect(parsed.default_mode).toBe("keyword");
    expect(parsed.max_entry_chars).toBe(8192);
    expect(parsed.chunk_size).toBe(512);
    expect(parsed.auto_update_sources).toBe(false);
  });

  test("accepts a vector config without any embedding block", () => {
    const parsed = knowledgeConfigSchema.parse({
      retrieval_modes: ["grep", "keyword", "vector"],
    });
    expect(parsed.retrieval_modes).toContain("vector");
  });

  test("rejects an unknown retrieval mode", () => {
    expect(knowledgeConfigSchema.safeParse({ retrieval_modes: ["semantic"] }).success).toBe(false);
  });

  test("rejects max_entry_chars below the floor (64)", () => {
    expect(knowledgeConfigSchema.safeParse({ max_entry_chars: 32 }).success).toBe(false);
  });

  test("rejects max_entry_chars above the ceiling (32768)", () => {
    expect(knowledgeConfigSchema.safeParse({ max_entry_chars: 65536 }).success).toBe(false);
  });

  test("rejects chunk_size below the floor (64)", () => {
    expect(knowledgeConfigSchema.safeParse({ chunk_size: 32 }).success).toBe(false);
  });

  test("rejects chunk_size above the ceiling (2048)", () => {
    expect(knowledgeConfigSchema.safeParse({ chunk_size: 4096 }).success).toBe(false);
  });

  test("rejects negative chunk_overlap", () => {
    expect(knowledgeConfigSchema.safeParse({ chunk_overlap: -1 }).success).toBe(false);
  });

  test("rejects max_document_bytes above 100 MB", () => {
    const result = knowledgeConfigSchema.safeParse({ max_document_bytes: 200 * 1024 * 1024 });
    expect(result.success).toBe(false);
  });
});

describe("addScopeFormSchema", () => {
  test("accepts a minimal valid form payload (defaults filled)", () => {
    const parsed = addScopeFormSchema.parse({ name: "design-notes" });
    expect(parsed.name).toBe("design-notes");
    expect(parsed.vector_enabled).toBe(false);
    expect(parsed.chunk_size).toBe(512);
    expect(parsed.max_document_mb).toBe(25);
  });

  test("accepts letters, digits, dashes, and underscores", () => {
    expect(addScopeFormSchema.safeParse({ name: "abc-123_XYZ" }).success).toBe(true);
  });

  test("rejects a name with disallowed characters", () => {
    expect(addScopeFormSchema.safeParse({ name: "bad name!" }).success).toBe(false);
  });

  test("rejects a name longer than 64 chars", () => {
    expect(addScopeFormSchema.safeParse({ name: "a".repeat(65) }).success).toBe(false);
  });

  test("rejects an empty name", () => {
    expect(addScopeFormSchema.safeParse({ name: "" }).success).toBe(false);
  });

  test("rejects 'global' — the auto-provisioned scope is never created by hand", () => {
    expect(addScopeFormSchema.safeParse({ name: "global" }).success).toBe(false);
  });

  test("rejects a project-<ULID> name — those auto-provision from the cwd", () => {
    const result = addScopeFormSchema.safeParse({ name: "project-01HXYZ" });
    expect(result.success).toBe(false);
  });
});

describe("addEntryFormSchema", () => {
  test("accepts a minimal entry (just text)", () => {
    expect(addEntryFormSchema.parse({ text: "uses tabs" }).text).toBe("uses tabs");
  });

  test("accepts title/description alongside the text", () => {
    const parsed = addEntryFormSchema.parse({
      text: "deploys via make release",
      title: "deploy",
      description: "how this repo ships",
    });
    expect(parsed.title).toBe("deploy");
    expect(parsed.description).toBe("how this repo ships");
  });

  test("rejects empty text", () => {
    expect(addEntryFormSchema.safeParse({ text: "" }).success).toBe(false);
  });

  test("rejects text over the 32768 char cap", () => {
    expect(addEntryFormSchema.safeParse({ text: "a".repeat(32769) }).success).toBe(false);
  });
});
