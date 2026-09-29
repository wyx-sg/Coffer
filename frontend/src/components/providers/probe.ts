// src/components/providers/probe.ts — how to call a saved provider's endpoint: its wire, URL and stored key's ref.
//
// The secret itself never leaves the daemon — only its reference is sent.
import type { Provider } from "@/lib/api/providers";
import type { ProviderProbe } from "@/lib/hooks/useModelIntrospection";

export function probeOf(
  provider: Pick<Provider, "protocol" | "base_url" | "credential_ref">,
): ProviderProbe {
  return {
    provider: provider.protocol,
    base_url: provider.base_url,
    credential_ref: provider.credential_ref,
  };
}
