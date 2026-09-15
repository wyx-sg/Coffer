// frontend/src/components/settings/providerFormSchema.ts
// The zod schema behind ProviderForm, built per render so every message is
// already translated: react-hook-form renders `issue.message` under the field
// verbatim, so the schema is where the copy has to be decided. Replaces the
// browser-native `required` attributes, whose bubbles are untranslated and
// which could not say "a full URL, please" about the endpoint.
import type { TFunction } from "i18next";
import { z } from "zod";

import { wireNeedsCredential } from "@/lib/api/providers";

const PROTOCOLS = ["anthropic", "openai", "ollama", "unknown"] as const;

export function providerFormSchema(t: TFunction, opts: { isEdit: boolean }) {
  return z
    .object({
      name: z.string().trim().min(1, t("settings.connections.errors.nameRequired")),
      presetId: z.string(),
      protocol: z.enum(PROTOCOLS),
      baseUrl: z.string().trim().url(t("settings.connections.errors.baseUrl")),
      secret: z.string(),
    })
    .superRefine((values, ctx) => {
      // A key is mandatory only when creating a keyed connection; on edit a
      // blank field means "keep the stored key", and ollama never has one.
      if (!opts.isEdit && wireNeedsCredential(values.protocol) && values.secret.length === 0) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["secret"],
          message: t("settings.connections.errors.secretRequired"),
        });
      }
    });
}

export type ProviderFormValues = z.input<ReturnType<typeof providerFormSchema>>;
