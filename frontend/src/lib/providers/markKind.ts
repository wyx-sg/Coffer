// src/lib/providers/markKind.ts — which official mark a provider is drawn with.
//
// Every preset vendor, and the runtimes detection finds (Ollama, LM Studio,
// vLLM, llama.cpp), has its mark (brandMarks.ts); a gateway or custom endpoint
// gets Coffer's neutral provider glyph beside its name. The vendor comes from
// the base URL (preset match, then the host), a local runtime from what
// detection recorded, and an `ollama`-protocol connection is Ollama whatever
// its URL says.
import type { Provider } from "@/lib/api/providers";
import type { BrandId } from "./brandMarks";
import { vendorOf } from "./presets";

export type ProviderMarkKind = BrandId | "glyph";

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

const onHost = (host: string, domain: string) => host === domain || host.endsWith(`.${domain}`);

export function providerMarkKind(
  provider: Pick<Provider, "base_url" | "protocol" | "local_runtime">,
): ProviderMarkKind {
  const runtime = provider.local_runtime?.runtime;
  if (runtime === "ollama") return "ollama";
  if (runtime === "vllm") return "vllm";
  if (runtime === "llama_server") return "llama-cpp";
  if (runtime === "lmstudio") return "lmstudio";
  if (provider.protocol === "ollama") return "ollama";
  const vendor = vendorOf(provider.base_url);
  if (vendor !== "custom") return vendor;
  const host = hostOf(provider.base_url);
  if (onHost(host, "anthropic.com")) return "anthropic";
  if (onHost(host, "openai.com")) return "openai";
  if (onHost(host, "openrouter.ai")) return "openrouter";
  return "glyph";
}
