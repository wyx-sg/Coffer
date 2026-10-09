// src/lib/providers/presets.ts — the vendor presets the Add dialog offers, and the vendor a saved provider reads as.
//
// A preset fills a vendor's addresses: the OpenAI-compatible one Codex uses
// and, where the vendor documents one, the Anthropic-compatible one Claude Code
// uses. Which agents the provider can serve follows from those addresses (ADRs
// one-connection-serves-both-wires, provider-reach-is-what-its-addresses-serve).
// A vendor whose mainland-China addresses differ names them in `cn`, and the Add
// dialog offers the region. Ollama and LM Studio are the local-runtime path: no
// key, a loopback address found by detection.
import type { Protocol } from "@/lib/api/providers";

export type PresetId =
  | "anthropic"
  | "openai"
  | "gemini"
  | "deepseek"
  | "openrouter"
  | "xai"
  | "mistral"
  | "groq"
  | "together"
  | "fireworks"
  | "kimi"
  | "zhipu"
  | "minimax"
  | "qwen"
  | "siliconflow"
  | "qianfan"
  | "hunyuan"
  | "stepfun"
  | "ollama"
  | "lmstudio"
  | "custom";

/** A vendor's addresses in one region. */
interface RegionAddresses {
  baseUrl: string;
  anthropicBaseUrl?: string;
}

export interface Preset {
  id: PresetId;
  /** The vendor's own brand name, identical in every locale; Custom's comes from i18n. */
  label: string;
  protocol: Protocol | "";
  baseUrl: string;
  /** Where this vendor serves the Anthropic wire too (on an openai preset). */
  anthropicBaseUrl?: string;
  /** The vendor's mainland-China addresses, where they differ (keys are per
   *  region); `baseUrl`/`anthropicBaseUrl` are then the international ones. */
  cn?: RegionAddresses;
  /** A runtime on this Mac: keyless, detected rather than typed. */
  local?: boolean;
  /** The detected runtime this vendor stands for (a local preset). */
  runtime?: "ollama" | "lmstudio";
}

/** In the order the Add dialog lists them. Addresses are the ones each
 *  vendor's own docs give (checked 2026-10-09); a vendor names an Anthropic
 *  address only where its docs document one for Claude Code. */
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
    anthropicBaseUrl: "https://openrouter.ai/api",
  },
  {
    id: "xai",
    label: "xAI",
    protocol: "openai",
    baseUrl: "https://api.x.ai/v1",
    anthropicBaseUrl: "https://api.x.ai",
  },
  { id: "mistral", label: "Mistral", protocol: "openai", baseUrl: "https://api.mistral.ai/v1" },
  { id: "groq", label: "Groq", protocol: "openai", baseUrl: "https://api.groq.com/openai/v1" },
  {
    id: "together",
    label: "Together AI",
    protocol: "openai",
    baseUrl: "https://api.together.ai/v1",
  },
  {
    id: "fireworks",
    label: "Fireworks AI",
    protocol: "openai",
    baseUrl: "https://api.fireworks.ai/inference/v1",
    anthropicBaseUrl: "https://api.fireworks.ai/inference",
  },
  {
    id: "kimi",
    label: "Kimi",
    protocol: "openai",
    baseUrl: "https://api.moonshot.ai/v1",
    anthropicBaseUrl: "https://api.moonshot.ai/anthropic",
    cn: {
      baseUrl: "https://api.moonshot.cn/v1",
      anthropicBaseUrl: "https://api.moonshot.cn/anthropic",
    },
  },
  {
    id: "zhipu",
    label: "Zhipu GLM",
    protocol: "openai",
    baseUrl: "https://api.z.ai/api/paas/v4/",
    anthropicBaseUrl: "https://api.z.ai/api/anthropic",
    cn: {
      baseUrl: "https://open.bigmodel.cn/api/paas/v4/",
      anthropicBaseUrl: "https://open.bigmodel.cn/api/anthropic",
    },
  },
  {
    id: "minimax",
    label: "MiniMax",
    protocol: "openai",
    baseUrl: "https://api.minimax.io/v1",
    anthropicBaseUrl: "https://api.minimax.io/anthropic",
    cn: {
      baseUrl: "https://api.minimax.cn/v1",
      anthropicBaseUrl: "https://api.minimax.cn/anthropic",
    },
  },
  {
    id: "qwen",
    label: "Qwen",
    protocol: "openai",
    baseUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    anthropicBaseUrl: "https://dashscope-intl.aliyuncs.com/apps/anthropic",
    cn: {
      baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
      anthropicBaseUrl: "https://dashscope.aliyuncs.com/apps/anthropic",
    },
  },
  {
    id: "siliconflow",
    label: "SiliconFlow",
    protocol: "openai",
    baseUrl: "https://api.siliconflow.com/v1",
    anthropicBaseUrl: "https://api.siliconflow.com",
    cn: {
      baseUrl: "https://api.siliconflow.cn/v1",
      anthropicBaseUrl: "https://api.siliconflow.cn",
    },
  },
  {
    id: "qianfan",
    label: "Baidu Qianfan",
    protocol: "openai",
    baseUrl: "https://qianfan.baidubce.com/v2",
    anthropicBaseUrl: "https://qianfan.baidubce.com/anthropic",
  },
  {
    id: "hunyuan",
    label: "Tencent Hunyuan",
    protocol: "openai",
    baseUrl: "https://api.hunyuan.cloud.tencent.com/v1",
    anthropicBaseUrl: "https://api.hunyuan.cloud.tencent.com/anthropic",
  },
  {
    id: "stepfun",
    label: "StepFun",
    protocol: "openai",
    baseUrl: "https://api.stepfun.com/v1",
    anthropicBaseUrl: "https://api.stepfun.com",
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
    [p.baseUrl, p.anthropicBaseUrl, p.cn?.baseUrl, p.cn?.anthropicBaseUrl].some(
      (u) => !!u && normaliseEndpoint(u) === wanted,
    ),
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

/** True for a loopback address — the only place a local runtime may live. */
export function isLoopbackUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.replace(/^\[|\]$/g, "");
    return host === "localhost" || host === "::1" || /^127\./.test(host);
  } catch {
    return false;
  }
}
