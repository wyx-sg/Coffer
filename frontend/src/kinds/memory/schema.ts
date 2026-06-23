// frontend/src/kinds/memory/schema.ts
//
// Zod schemas for the redesigned `memory` kind (spec 007). Stores are
// auto-provisioned, so there is no create form. There is NO llm_provider:
// facts are written directly. We pin the mutable store-config patch shape and
// the add-fact form (title/description/body). There is no `type` — Lane is the
// only memory taxonomy (spec 007 FR-048).
import { z } from "zod";

export const retrievalModeSchema = z.enum(["grep", "keyword", "vector"]);

export const memoryStoreConfigSchema = z.object({
  retrieval_modes: z.array(retrievalModeSchema).default(["grep", "keyword"]),
  default_mode: retrievalModeSchema.default("keyword"),
  embedding_provider: z.string().nullable().optional(),
  embedding_model: z.string().nullable().optional(),
  embedding_base_url: z.string().nullable().optional(),
  embedding_credential_ref: z.string().nullable().optional(),
  embedding_dimensions: z.number().int().min(1).max(8192).default(768),
  max_fact_chars: z.number().int().min(64).max(32768).default(8192),
});

export const addFactFormSchema = z.object({
  text: z.string().min(1, "fact text required").max(32768),
  title: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
});

export type AddFactFormInput = z.input<typeof addFactFormSchema>;
export type AddFactFormValues = z.output<typeof addFactFormSchema>;
