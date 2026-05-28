// frontend/src/kinds/knowledge_base/schema.ts
import { z } from "zod";

export const knowledgeBaseConfigSchema = z.object({
  embedding_model: z.string().min(1, "embedding model required"),
  chunk_size: z.number().int().min(64).max(2048).default(512),
  chunk_overlap: z.number().int().min(0).max(1024).default(64),
  max_document_bytes: z
    .number()
    .int()
    .min(1024)
    .max(100 * 1024 * 1024)
    .default(25 * 1024 * 1024),
});

export const addKnowledgeBaseFormSchema = z.object({
  name: z
    .string()
    .min(1, "name required")
    .max(64)
    .regex(/^[a-zA-Z0-9_-]+$/, "letters, digits, dash, underscore only"),
  description: z.string().nullable().optional(),
  embedding_model: z.string().min(1, "embedding model required").default("BAAI/bge-small-en-v1.5"),
  chunk_size: z.number().int().min(64).max(2048).default(512),
  chunk_overlap: z.number().int().min(0).max(1024).default(64),
  max_document_mb: z.number().int().min(1).max(100).default(25),
});

export type AddKnowledgeBaseFormInput = z.input<typeof addKnowledgeBaseFormSchema>;
export type AddKnowledgeBaseFormValues = z.output<typeof addKnowledgeBaseFormSchema>;
