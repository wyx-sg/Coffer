// frontend/src/kinds/knowledge_base/schema.test.ts — TEST22-019
//
// Pin the Zod schemas in `schema.ts`. They drive both the add-KB form and
// the on-disk persisted config shape; a regression here yields silent
// drift between the frontend form and the backend OpenAPI contract.

import { describe, expect, test } from "vitest";
import { addKnowledgeBaseFormSchema, knowledgeBaseConfigSchema } from "./schema";

describe("knowledgeBaseConfigSchema", () => {
  test("accepts a fully-specified config", () => {
    const parsed = knowledgeBaseConfigSchema.parse({
      embedding_model: "BAAI/bge-small-en-v1.5",
      chunk_size: 512,
      chunk_overlap: 64,
      max_document_bytes: 1024 * 1024,
    });
    expect(parsed.embedding_model).toBe("BAAI/bge-small-en-v1.5");
    expect(parsed.chunk_size).toBe(512);
  });

  test("rejects an empty embedding_model", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      embedding_model: "",
      chunk_size: 512,
      chunk_overlap: 64,
      max_document_bytes: 1024 * 1024,
    });
    expect(result.success).toBe(false);
  });

  test("rejects chunk_size below the floor (64)", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      embedding_model: "m",
      chunk_size: 32, // below min 64
      chunk_overlap: 0,
      max_document_bytes: 1024,
    });
    expect(result.success).toBe(false);
  });

  test("rejects chunk_size above the ceiling (2048)", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      embedding_model: "m",
      chunk_size: 4096, // above max 2048
      chunk_overlap: 0,
      max_document_bytes: 1024,
    });
    expect(result.success).toBe(false);
  });

  test("rejects negative chunk_overlap", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      embedding_model: "m",
      chunk_size: 512,
      chunk_overlap: -1,
      max_document_bytes: 1024,
    });
    expect(result.success).toBe(false);
  });

  test("rejects max_document_bytes above 100 MB", () => {
    const result = knowledgeBaseConfigSchema.safeParse({
      embedding_model: "m",
      chunk_size: 512,
      chunk_overlap: 64,
      max_document_bytes: 200 * 1024 * 1024,
    });
    expect(result.success).toBe(false);
  });
});

describe("addKnowledgeBaseFormSchema", () => {
  test("accepts a minimal valid form payload (defaults filled)", () => {
    const parsed = addKnowledgeBaseFormSchema.parse({
      name: "design-notes",
    });
    expect(parsed.name).toBe("design-notes");
    expect(parsed.embedding_model).toBe("BAAI/bge-small-en-v1.5");
    expect(parsed.chunk_size).toBe(512);
    expect(parsed.chunk_overlap).toBe(64);
    expect(parsed.max_document_mb).toBe(25);
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
    const r = addKnowledgeBaseFormSchema.safeParse({
      name: "kb-1_design",
    });
    expect(r.success).toBe(true);
  });

  test("clamps max_document_mb to its allowed range", () => {
    const tooBig = addKnowledgeBaseFormSchema.safeParse({
      name: "k",
      max_document_mb: 1000,
    });
    expect(tooBig.success).toBe(false);
    const tooSmall = addKnowledgeBaseFormSchema.safeParse({
      name: "k",
      max_document_mb: 0,
    });
    expect(tooSmall.success).toBe(false);
  });
});
