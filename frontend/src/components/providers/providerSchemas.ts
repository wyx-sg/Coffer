// src/components/providers/providerSchemas.ts — the zod schemas behind the Add and Edit dialogs.
//
// Built per render so every message is already translated: react-hook-form
// renders `issue.message` under the field verbatim. The endpoint must be a
// full URL before anything is sent; a keyed provider needs its key on create;
// a local runtime must be on this machine. A remote connection names at least
// one of its two addresses (ADR one-connection-serves-both-wires).
import type { SecretFieldValue } from "@/lib/secretValue";
import type { TFunction } from "i18next";
import { z } from "zod";

import { isLoopbackUrl } from "@/lib/providers/presets";

const PROTOCOLS = ["anthropic", "openai", "ollama", "unknown"] as const;

/** Each typed address is a URL, and at least one is typed. */
function checkAddresses(
  t: TFunction,
  v: { openaiUrl: string; anthropicUrl: string },
  ctx: z.RefinementCtx,
) {
  const typed = (["openaiUrl", "anthropicUrl"] as const).filter((k) => v[k].trim() !== "");
  if (typed.length === 0) {
    ctx.addIssue({ code: "custom", path: ["openaiUrl"], message: t("providers.errors.address") });
    return;
  }
  for (const k of typed) {
    if (!z.string().url().safeParse(v[k].trim()).success) {
      ctx.addIssue({ code: "custom", path: [k], message: t("providers.errors.baseUrl") });
    }
  }
}

export function editSchema(t: TFunction) {
  return z
    .object({
      name: z.string().trim().min(1, t("providers.errors.nameRequired")),
      openaiUrl: z.string(),
      anthropicUrl: z.string(),
    })
    .superRefine((v, ctx) => checkAddresses(t, v, ctx));
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
      /** Remote: where Codex (OpenAI wire) and Claude Code (Anthropic wire) reach it. */
      openaiUrl: z.string(),
      anthropicUrl: z.string(),
      /** The key: a stored secret, or a new value stored when the provider is added. */
      secret: z.custom<SecretFieldValue>(),
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
      checkAddresses(t, v, ctx);
      if (v.secret === null || (v.secret.kind === "new" && v.secret.value === "")) {
        ctx.addIssue({
          code: "custom",
          path: ["secret"],
          message: t("providers.errors.secretRequired"),
        });
      }
    });
}

export type EndpointValues = z.input<ReturnType<typeof endpointSchema>>;
