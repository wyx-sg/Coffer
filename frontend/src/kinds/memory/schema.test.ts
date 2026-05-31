// frontend/src/kinds/memory/schema.test.ts — TEST26-014
//
// Pin the Zod schemas in `schema.ts`. They drive both the add-memory-store
// form and the on-disk persisted config shape; a regression here yields
// silent drift between the frontend form and the backend OpenAPI contract.

import { describe, expect, test } from "vitest";
import { addMemoryStoreFormSchema, memoryStoreConfigSchema } from "./schema";

describe("memoryStoreConfigSchema", () => {
  test("accepts a fully-specified ollama config", () => {
    const parsed = memoryStoreConfigSchema.parse({
      embedding_model: "BAAI/bge-small-en-v1.5",
      llm_provider: "ollama",
      llm_model: "llama3.1",
      llm_endpoint: "http://localhost:11434",
      llm_credential_ref: null,
      max_memory_chars: 8192,
    });
    expect(parsed.llm_provider).toBe("ollama");
    expect(parsed.embedding_model).toBe("BAAI/bge-small-en-v1.5");
  });

  test("accepts an empty config and fills defaults", () => {
    const parsed = memoryStoreConfigSchema.parse({});
    expect(parsed.embedding_model).toBe("BAAI/bge-small-en-v1.5");
    expect(parsed.llm_provider).toBe("none");
    expect(parsed.max_memory_chars).toBe(8192);
  });

  test("rejects an empty embedding_model", () => {
    const result = memoryStoreConfigSchema.safeParse({
      embedding_model: "",
      llm_provider: "none",
    });
    expect(result.success).toBe(false);
  });

  test("rejects an unknown llm_provider", () => {
    const result = memoryStoreConfigSchema.safeParse({
      llm_provider: "anthropic",
    });
    expect(result.success).toBe(false);
  });

  test("rejects max_memory_chars below the floor (64)", () => {
    const result = memoryStoreConfigSchema.safeParse({
      max_memory_chars: 32,
    });
    expect(result.success).toBe(false);
  });

  test("rejects max_memory_chars above the ceiling (32768)", () => {
    const result = memoryStoreConfigSchema.safeParse({
      max_memory_chars: 65536,
    });
    expect(result.success).toBe(false);
  });
});

describe("addMemoryStoreFormSchema", () => {
  test("accepts a minimal valid form payload (defaults filled)", () => {
    const parsed = addMemoryStoreFormSchema.parse({ name: "coding-prefs" });
    expect(parsed.name).toBe("coding-prefs");
    expect(parsed.embedding_model).toBe("BAAI/bge-small-en-v1.5");
    expect(parsed.llm_provider).toBe("none");
    expect(parsed.max_memory_chars).toBe(8192);
  });

  test("rejects a name with disallowed characters", () => {
    const r = addMemoryStoreFormSchema.safeParse({ name: "bad name!" });
    expect(r.success).toBe(false);
  });

  test("rejects a name longer than 64 chars", () => {
    const r = addMemoryStoreFormSchema.safeParse({ name: "a".repeat(65) });
    expect(r.success).toBe(false);
  });

  test("rejects an empty name", () => {
    const r = addMemoryStoreFormSchema.safeParse({ name: "" });
    expect(r.success).toBe(false);
  });

  test("accepts letters, digits, dashes, and underscores", () => {
    const r = addMemoryStoreFormSchema.safeParse({ name: "mem-1_store" });
    expect(r.success).toBe(true);
  });

  test("propagates llm_provider through the form schema", () => {
    const r = addMemoryStoreFormSchema.parse({
      name: "m",
      llm_provider: "ollama",
      llm_model: "llama3.1",
    });
    expect(r.llm_provider).toBe("ollama");
    expect(r.llm_model).toBe("llama3.1");
  });
});
