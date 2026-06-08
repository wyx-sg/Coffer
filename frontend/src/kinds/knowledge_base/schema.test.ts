// frontend/src/kinds/knowledge_base/schema.test.ts
//
// Pin the Zod schemas in `schema.ts`. They drive the add-KB form and the
// persisted retrieval config; a regression here yields silent drift between
// the frontend form and the backend OpenAPI contract.

import { describe, expect, test } from "vitest";
import { addKnowledgeBaseFormSchema, knowledgeBaseConfigSchema } from "./schema";

describe("knowledgeBaseConfigSchema", () => {
  test("accepts a keyword/grep config with defaults", () => {
    const parsed = knowledgeBaseConfigSchema.parse({});
    expect(parsed.enabled_modes).toEqual(["keyword", "grep"]);
    expect(parsed.default_mode).toBe("keyword");
    expect(parsed.chunk_size).toBe(512);
  });

  test("accepts a vector config with an embedding block", () => {
    const parsed = knowledgeBaseConfigSchema.parse({
      enabled_modes: ["keyword", "grep", "vector"],
      embedding: { provider: "local", model: "bge-m3", dimensions: 1024 },
    });
    expect(parsed.enabled_modes).toContain("vector");
    expect(parsed.embedding?.model).toBe("bge-m3");
  });

  test("rejects vector mode without an embedding block", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      enabled_modes: ["keyword", "vector"],
    });
    expect(result.success).toBe(false);
  });

  test("rejects chunk_size below the floor (64)", () => {
    const result = knowledgeBaseConfigSchema.safeParse({ chunk_size: 32 });
    expect(result.success).toBe(false);
  });

  test("rejects chunk_size above the ceiling (2048)", () => {
    const result = knowledgeBaseConfigSchema.safeParse({ chunk_size: 4096 });
    expect(result.success).toBe(false);
  });

  test("rejects negative chunk_overlap", () => {
    const result = knowledgeBaseConfigSchema.safeParse({ chunk_overlap: -1 });
    expect(result.success).toBe(false);
  });

  test("rejects max_document_bytes above 100 MB", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      max_document_bytes: 200 * 1024 * 1024,
    });
    expect(result.success).toBe(false);
  });
});

describe("addKnowledgeBaseFormSchema", () => {
  test("accepts a minimal valid form payload (defaults filled)", () => {
    const parsed = addKnowledgeBaseFormSchema.parse({ name: "design-notes" });
    expect(parsed.name).toBe("design-notes");
    expect(parsed.vector_enabled).toBe(false);
    expect(parsed.chunk_size).toBe(512);
    expect(parsed.max_document_mb).toBe(25);
  });

  test("requires a provider + model when vector is enabled", () => {
    const ok = addKnowledgeBaseFormSchema.safeParse({
      name: "k",
      vector_enabled: true,
      embedding_provider: "local",
      embedding_model: "bge-m3",
    });
    expect(ok.success).toBe(true);

    const bad = addKnowledgeBaseFormSchema.safeParse({
      name: "k",
      vector_enabled: true,
      embedding_provider: "",
      embedding_model: "",
    });
    expect(bad.success).toBe(false);
  });

  test("rejects a name with disallowed characters", () => {
    const r = addKnowledgeBaseFormSchema.safeParse({ name: "bad name!" });
    expect(r.success).toBe(false);
  });

  test("rejects a name longer than 64 chars", () => {
    const r = addKnowledgeBaseFormSchema.safeParse({ name: "a".repeat(65) });
    expect(r.success).toBe(false);
  });

  test("rejects an empty name", () => {
    const r = addKnowledgeBaseFormSchema.safeParse({ name: "" });
    expect(r.success).toBe(false);
  });

  test("accepts letters, digits, dashes, and underscores", () => {
    const r = addKnowledgeBaseFormSchema.safeParse({ name: "kb-1_design" });
    expect(r.success).toBe(true);
  });

  test("clamps max_document_mb to its allowed range", () => {
    expect(addKnowledgeBaseFormSchema.safeParse({ name: "k", max_document_mb: 1000 }).success).toBe(
      false,
    );
    expect(addKnowledgeBaseFormSchema.safeParse({ name: "k", max_document_mb: 0 }).success).toBe(
      false,
    );
  });
});
