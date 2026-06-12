// components/settings/modelSchema.ts — zod schema for ModelForm
import { z } from "zod";

export const modelSchema = z
  .object({
    display_name: z.string().min(1, "required"),
    provider: z.enum(["anthropic", "openai", "ollama"]),
    model: z.string().min(1, "required"),
    credential_ref: z.string().nullable().optional(),
    base_url: z.string().url("must be a valid URL").nullable().optional().or(z.literal("")),
    is_default: z.boolean().optional(),
  })
  .superRefine((data, ctx) => {
    // Non-ollama providers require a credential reference (API key name).
    if (data.provider !== "ollama" && !data.credential_ref?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["credential_ref"],
        message: "API credential reference is required for this provider",
      });
    }
    // Ollama requires a base URL pointing to the local inference server.
    if (data.provider === "ollama" && !data.base_url?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["base_url"],
        message: "Base URL is required for Ollama (e.g. http://localhost:11434)",
      });
    }
  });

export type ModelFormValues = z.infer<typeof modelSchema>;
