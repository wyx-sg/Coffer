// src/components/providers/probe.ts — how to call a saved provider's endpoint: its wire, URL and stored key's ref.
//
// The secret itself never leaves the daemon — only its reference is sent.
import type { ListModelsIn, Provider } from "@/lib/api/providers";

export function probeOf(
  provider: Pick<Provider, "protocol" | "base_url" | "secret_ref">,
): ListModelsIn {
  return {
    provider: provider.protocol,
    base_url: provider.base_url,
    secret_ref: provider.secret_ref,
  };
}
