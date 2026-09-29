// src/lib/providers/markKind.ts — which official mark a provider is drawn with.
//
// Official marks exist for Anthropic, OpenAI, OpenRouter, Ollama, vLLM and
// llama.cpp; every other provider (Bedrock, Gemini, DeepSeek, LM Studio,
// gateways, custom) gets Coffer's neutral provider glyph beside its name. The vendor comes from the base URL (preset
// match, then the host), a local runtime from what detection recorded, and an
// `ollama`-protocol connection is Ollama whatever its URL says.
import type { Provider } from "@/lib/api/providers";
import { vendorOf } from "./presets";

export type ProviderMarkKind =
  | "anthropic"
  | "openai"
  | "openrouter"
  | "ollama"
  | "vllm"
  | "llama-cpp"
  | "glyph";

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
  if (runtime === "lmstudio") return "glyph";
  if (provider.protocol === "ollama") return "ollama";
  const vendor = vendorOf(provider.base_url);
  if (vendor === "anthropic" || vendor === "openai" || vendor === "ollama") return vendor;
  if (vendor === "openrouter") return "openrouter";
  const host = hostOf(provider.base_url);
  if (onHost(host, "anthropic.com")) return "anthropic";
  if (onHost(host, "openai.com")) return "openai";
  if (onHost(host, "openrouter.ai")) return "openrouter";
  return "glyph";
}
