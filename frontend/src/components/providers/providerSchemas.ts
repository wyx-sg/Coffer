// src/components/providers/providerSchemas.ts — the zod schemas behind the Add and Edit dialogs.
//
// Built per render so every message is already translated: react-hook-form
// renders `issue.message` under the field verbatim. The endpoint must be a
// full URL before anything is sent; a keyed provider needs its key on create;
// a local runtime must be on this machine.
import type { TFunction } from "i18next";
import { z } from "zod";

import { isLoopbackUrl } from "@/lib/providers/presets";

const PROTOCOLS = ["anthropic", "openai", "ollama", "unknown"] as const;

export function editSchema(t: TFunction) {
  return z.object({
    name: z.string().trim().min(1, t("providers.errors.nameRequired")),
    protocol: z.enum(PROTOCOLS),
    baseUrl: z.string().trim().url(t("providers.errors.baseUrl")),
  });
}

export type EditValues = z.input<ReturnType<typeof editSchema>>;

export function endpointSchema(t: TFunction) {
  return z
    .object({
      /** The local-runtime path: keyless, a loopback address found by detection. */
      local: z.boolean(),
      name: z.string().trim().min(1, t("providers.errors.nameRequired")),
      protocol: z.enum(PROTOCOLS),
      // Local: blank means "look on each runtime's default port".
      baseUrl: z.string().trim(),
      secret: z.string(),
    })
    .superRefine((v, ctx) => {
      const url = v.baseUrl;
      if (v.local) {
        if (url && !isLoopbackUrl(url)) {
          ctx.addIssue({
            code: "custom",
            path: ["baseUrl"],
            message: t("providers.errors.loopback"),
          });
        }
        return;
      }
      if (!z.string().url().safeParse(url).success) {
        ctx.addIssue({ code: "custom", path: ["baseUrl"], message: t("providers.errors.baseUrl") });
      }
      if (v.secret.length === 0) {
        ctx.addIssue({
          code: "custom",
          path: ["secret"],
          message: t("providers.errors.secretRequired"),
        });
      }
    });
}

export type EndpointValues = z.input<ReturnType<typeof endpointSchema>>;
