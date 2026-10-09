// src/lib/providers/presets.ts — the vendor presets the Add dialog offers, and the vendor a saved provider reads as.
//
// A preset fills the endpoint and protocol; which agents the provider reaches
// is not decided here — that is the resource's per-agent scope, owned by the
// shared ScopeControl (the wire's own default is applied server-side when the
// provider is created). OpenAI-compatible gateways (Gemini, DeepSeek,
// OpenRouter) use the openai protocol. Ollama is the local-runtime path: no
// key, a loopback address found by detection. A vendor that serves the
// Anthropic wire at a different root (DeepSeek's `/anthropic`) names it, and
// the Add dialog offers both wires: one connection is one endpoint, so
// reaching Claude Code and Codex there takes two connections (ADR
// one-connection-is-one-endpoint).
import type { Protocol } from "@/lib/api/providers";

export type PresetId =
  | "anthropic"
  | "openai"
  | "gemini"
  | "deepseek"
  | "openrouter"
  | "ollama"
  | "lmstudio"
  | "custom";

export interface Preset {
  id: PresetId;
  /** The vendor's own brand name, identical in every locale; Custom's comes from i18n. */
  label: string;
  protocol: Protocol | "";
  baseUrl: string;
  /** Where this vendor serves the Anthropic wire, when not at `baseUrl`. */
  anthropicBaseUrl?: string;
  /** A runtime on this Mac: keyless, detected rather than typed. */
  local?: boolean;
  /** The detected runtime this vendor stands for (a local preset). */
  runtime?: "ollama" | "lmstudio";
}

/** In the order the Add dialog lists them. */
export const PRESETS: readonly Preset[] = [
  {
    id: "anthropic",
    label: "Anthropic",
    protocol: "anthropic",
    baseUrl: "https://api.anthropic.com",
  },
  { id: "openai", label: "OpenAI", protocol: "openai", baseUrl: "https://api.openai.com/v1" },
  {
    id: "gemini",
    label: "Google Gemini",
    protocol: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    protocol: "openai",
    baseUrl: "https://api.deepseek.com",
    anthropicBaseUrl: "https://api.deepseek.com/anthropic",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    protocol: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
  },
  {
    id: "ollama",
    label: "Ollama",
    protocol: "openai",
    baseUrl: "http://localhost:11434",
    local: true,
    runtime: "ollama",
  },
  {
    id: "lmstudio",
    label: "LM Studio",
    protocol: "openai",
    baseUrl: "",
    local: true,
    runtime: "lmstudio",
  },
  { id: "custom", label: "Custom", protocol: "", baseUrl: "" },
];

export function presetById(id: PresetId): Preset {
  return PRESETS.find((p) => p.id === id) ?? PRESETS[PRESETS.length - 1];
}

// Endpoints differ only cosmetically between a preset and what was stored —
// case and a trailing slash carry no meaning.
function normaliseEndpoint(url: string): string {
  return url.trim().toLowerCase().replace(/\/+$/, "");
}

/**
 * Which vendor a saved provider belongs to. Nothing stores a vendor: the
 * presets only seed the form, so the endpoint is the evidence left — the saved
 * base URL matched back against PRESETS. Editing a preset's endpoint (a proxy
 * in front of OpenAI, say) makes it read as Custom, which is honest: from
 * Coffer's side it is no longer the vendor's own endpoint.
 */
export function vendorOf(baseUrl: string): PresetId {
  const wanted = normaliseEndpoint(baseUrl);
  const hit = PRESETS.find((p) =>
    [p.baseUrl, p.anthropicBaseUrl ?? ""].some((u) => u !== "" && normaliseEndpoint(u) === wanted),
  );
  return hit ? hit.id : "custom";
}

/** One display label per protocol, shared by every surface that names a wire
 *  (`ollama` is retired: it labels a stored connection and is never offered). */
export const PROTOCOL_LABEL_KEY: Record<Protocol, string> = {
  anthropic: "providers.protocols.anthropic",
  openai: "providers.protocols.openai",
  ollama: "providers.protocols.ollama",
  unknown: "providers.protocols.unknown",
};

/** The protocols a Custom endpoint, or a vendor with two wire roots, picks from. */
export const CUSTOM_PROTOCOLS: readonly Protocol[] = ["openai", "anthropic"] as const;

/** The protocols a provider's Edit dialog may correct it to. A stored retired
 *  `ollama` value is still shown, by the dialog, but never offered. */
export const EDITABLE_PROTOCOLS: readonly Protocol[] = ["openai", "anthropic"] as const;

/** The base URL `preset` serves `protocol` at. */
export function presetBaseUrl(preset: Preset, protocol: Protocol): string {
  return protocol === "anthropic" && preset.anthropicBaseUrl
    ? preset.anthropicBaseUrl
    : preset.baseUrl;
}

/** True for a loopback address — the only place a local runtime may live. */
export function isLoopbackUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^\[|\]$/g, "");
    return host === "localhost" || host === "::1" || /^127\./.test(host);
  } catch {
    return false;
  }
}
