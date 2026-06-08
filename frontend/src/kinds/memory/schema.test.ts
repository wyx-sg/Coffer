// frontend/src/kinds/memory/schema.test.ts
//
// Pin the Zod schemas in `schema.ts`. Stores are auto-provisioned (no create
// form) and there is NO llm_provider anymore; we pin the mutable store-config
// patch shape and the add-fact form (name/description/body/type).

import { describe, expect, test } from "vitest";
import { addFactFormSchema, memoryStoreConfigSchema } from "./schema";

describe("memoryStoreConfigSchema", () => {
  test("accepts an empty config and fills defaults", () => {
    const parsed = memoryStoreConfigSchema.parse({});
    expect(parsed.retrieval_modes).toEqual(["grep", "keyword"]);
    expect(parsed.default_mode).toBe("keyword");
    expect(parsed.max_fact_chars).toBe(8192);
  });

  test("accepts a vector config with embedding fields", () => {
    const parsed = memoryStoreConfigSchema.parse({
      retrieval_modes: ["grep", "keyword", "vector"],
      embedding_provider: "local",
      embedding_model: "bge-m3",
    });
    expect(parsed.retrieval_modes).toContain("vector");
    expect(parsed.embedding_model).toBe("bge-m3");
  });

  test("rejects an unknown retrieval mode", () => {
    const result = memoryStoreConfigSchema.safeParse({ retrieval_modes: ["semantic"] });
    expect(result.success).toBe(false);
  });

  test("rejects max_fact_chars below the floor (64)", () => {
    expect(memoryStoreConfigSchema.safeParse({ max_fact_chars: 32 }).success).toBe(false);
  });

  test("rejects max_fact_chars above the ceiling (32768)", () => {
    expect(memoryStoreConfigSchema.safeParse({ max_fact_chars: 65536 }).success).toBe(false);
  });
});

describe("addFactFormSchema", () => {
  test("accepts a minimal fact (just text)", () => {
    const parsed = addFactFormSchema.parse({ text: "uses tabs" });
    expect(parsed.text).toBe("uses tabs");
  });

  test("accepts name/description/type alongside the text", () => {
    const parsed = addFactFormSchema.parse({
      text: "deploys via make release",
      name: "deploy",
      description: "how this repo ships",
      type: "project",
    });
    expect(parsed.name).toBe("deploy");
    expect(parsed.type).toBe("project");
  });

  test("rejects empty text", () => {
    expect(addFactFormSchema.safeParse({ text: "" }).success).toBe(false);
  });

  test("rejects text over the 32768 char cap", () => {
    expect(addFactFormSchema.safeParse({ text: "a".repeat(32769) }).success).toBe(false);
  });
});
