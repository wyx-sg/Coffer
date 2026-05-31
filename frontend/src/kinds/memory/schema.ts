// frontend/src/kinds/memory/schema.ts
import { z } from "zod";

export const llmProviderSchema = z.enum(["none", "ollama", "openai"]);

export const memoryStoreConfigSchema = z.object({
  embedding_model: z.string().min(1).default("BAAI/bge-small-en-v1.5"),
  llm_provider: llmProviderSchema.default("none"),
  llm_model: z.string().nullable().optional(),
  llm_endpoint: z.string().nullable().optional(),
  llm_credential_ref: z.string().nullable().optional(),
  max_memory_chars: z.number().int().min(64).max(32768).default(8192),
});

export const addMemoryStoreFormSchema = z.object({
  name: z
    .string()
    .min(1)
    .max(64)
    .regex(/^[a-zA-Z0-9_-]+$/),
  description: z.string().nullable().optional(),
  embedding_model: z.string().min(1).default("BAAI/bge-small-en-v1.5"),
  llm_provider: llmProviderSchema.default("none"),
  llm_model: z.string().nullable().optional(),
  llm_endpoint: z.string().nullable().optional(),
  llm_credential_ref: z.string().nullable().optional(),
  max_memory_chars: z.number().int().min(64).max(32768).default(8192),
});

export type AddMemoryStoreFormInput = z.input<typeof addMemoryStoreFormSchema>;
export type AddMemoryStoreFormValues = z.output<typeof addMemoryStoreFormSchema>;
