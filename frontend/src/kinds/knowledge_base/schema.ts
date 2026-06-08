// frontend/src/kinds/knowledge_base/schema.ts
//
// Zod schemas driving the add-KB form + the persisted config shape. Mirrors the
// redesigned OpenAPI contract: retrieval modes (grep/keyword/vector), chunk
// params, and an OPTIONAL embedding config required only when `vector` is an
// enabled mode.
import { z } from "zod";

export const retrievalModeSchema = z.enum(["grep", "keyword", "vector"]);

export const embeddingConfigSchema = z.object({
  provider: z.string().min(1, "provider required"),
  model: z.string().min(1, "model required"),
  base_url: z.string().nullable().optional(),
  credential_ref: z.string().nullable().optional(),
  dimensions: z.number().int().min(1).default(1024),
});

export const knowledgeBaseConfigSchema = z
  .object({
    enabled_modes: z.array(retrievalModeSchema).default(["keyword", "grep"]),
    default_mode: retrievalModeSchema.default("keyword"),
    chunk_size: z.number().int().min(64).max(2048).default(512),
    chunk_overlap: z.number().int().min(0).max(1024).default(64),
    max_document_bytes: z
      .number()
      .int()
      .min(1024)
      .max(100 * 1024 * 1024)
      .default(25 * 1024 * 1024),
    embedding: embeddingConfigSchema.nullable().optional(),
  })
  .refine((c) => !c.enabled_modes.includes("vector") || c.embedding != null, {
    message: "vector mode requires an embedding config",
    path: ["embedding"],
  });

export const addKnowledgeBaseFormSchema = z
  .object({
    name: z
      .string()
      .min(1, "name required")
      .max(64)
      .regex(/^[a-zA-Z0-9_-]+$/, "letters, digits, dash, underscore only"),
    description: z.string().nullable().optional(),
    vector_enabled: z.boolean().default(false),
    embedding_provider: z.string().default("local"),
    embedding_model: z.string().default("bge-m3"),
    embedding_base_url: z.string().nullable().optional(),
    embedding_credential_ref: z.string().nullable().optional(),
    embedding_dimensions: z.number().int().min(1).default(1024),
    chunk_size: z.number().int().min(64).max(2048).default(512),
    chunk_overlap: z.number().int().min(0).max(1024).default(64),
    max_document_mb: z.number().int().min(1).max(100).default(25),
  })
  .refine(
    (f) => !f.vector_enabled || (f.embedding_provider.length > 0 && f.embedding_model.length > 0),
    {
      message: "vector mode requires an embedding provider + model",
      path: ["embedding_model"],
    },
  );

export type AddKnowledgeBaseFormInput = z.input<typeof addKnowledgeBaseFormSchema>;
export type AddKnowledgeBaseFormValues = z.output<typeof addKnowledgeBaseFormSchema>;
