// frontend/src/kinds/knowledge/schema.ts
//
// Zod schemas for the one `knowledge` kind: the persisted per-scope config, the
// "new collection" form, and the add-entry form.
//
// There are NO embedding fields. Both former kinds carried their own
// (`embedding_*` flat on memory, a nested `embedding` block on the knowledge
// base) and neither was read by the time they merged: embedding resolves
// through the installation-wide config (Settings → Embedding), and a scope opts
// into semantic search purely by listing `vector` in `retrieval_modes`.
//
// The create form only ever makes a NAMED collection: `global` and
// `project-<ULID>` auto-provision on first use and the backend rejects them
// with 422, so the name field refuses those shapes client-side too.
import { z } from "zod";

import { GLOBAL_SCOPE_NAME, PROJECT_SCOPE_PREFIX } from "./types";

export const retrievalModeSchema = z.enum(["grep", "keyword", "vector", "hybrid"]);

export const knowledgeConfigSchema = z.object({
  retrieval_modes: z.array(retrievalModeSchema).default(["grep", "keyword"]),
  default_mode: retrievalModeSchema.default("keyword"),
  max_entry_chars: z.number().int().min(64).max(32768).default(8192),
  chunk_size: z.number().int().min(64).max(2048).default(512),
  chunk_overlap: z.number().int().min(0).max(1024).default(64),
  max_document_bytes: z
    .number()
    .int()
    .min(1024)
    .max(100 * 1024 * 1024)
    .default(25 * 1024 * 1024),
  auto_update_sources: z.boolean().default(false),
});

/** A collection name the user may type: never an auto-provisioned scope. */
export const scopeNameSchema = z
  .string()
  .min(1, "name required")
  .max(64)
  .regex(/^[a-zA-Z0-9_-]+$/, "letters, digits, dash, underscore only")
  .refine((v) => v !== GLOBAL_SCOPE_NAME, {
    message: "'global' is provisioned automatically",
  })
  .refine((v) => !v.startsWith(PROJECT_SCOPE_PREFIX), {
    message: "project scopes are provisioned automatically",
  });

export const addScopeFormSchema = z.object({
  name: scopeNameSchema,
  description: z.string().nullable().optional(),
  vector_enabled: z.boolean().default(false),
  chunk_size: z.number().int().min(64).max(2048).default(512),
  chunk_overlap: z.number().int().min(0).max(1024).default(64),
  max_document_mb: z.number().int().min(1).max(100).default(25),
});

export const addEntryFormSchema = z.object({
  text: z.string().min(1, "entry text required").max(32768),
  title: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
});

export type AddScopeFormInput = z.input<typeof addScopeFormSchema>;
export type AddScopeFormValues = z.output<typeof addScopeFormSchema>;
export type AddEntryFormInput = z.input<typeof addEntryFormSchema>;
export type AddEntryFormValues = z.output<typeof addEntryFormSchema>;
