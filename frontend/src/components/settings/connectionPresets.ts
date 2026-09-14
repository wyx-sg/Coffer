// components/settings/connectionPresets.ts — provider presets for the add-
// connection form. A preset fills the endpoint + protocol; which agents the
// connection reaches is not decided here at all — that is the resource's
// framework per-agent scope, owned by the shared ScopeControl (the wire's own
// default is applied server-side by `Kind.default_scope` when the connection is
// created).
import type { AgentType, Protocol } from "@/lib/api/providers";

export interface Preset {
  id: string;
  label: string;
  protocol: Protocol | "";
  baseUrl: string;
}

// OpenAI-compatible gateways (Gemini, DeepSeek, …) use the openai protocol —
// agent compatibility is decided separately via the checkboxes.
export const PRESETS: Preset[] = [
  { id: "openai", label: "OpenAI", protocol: "openai", baseUrl: "https://api.openai.com/v1" },
  {
    id: "anthropic",
    label: "Anthropic",
    protocol: "anthropic",
    baseUrl: "https://api.anthropic.com",
  },
  {
    id: "gemini",
    label: "Google Gemini",
    protocol: "openai",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
  },
  { id: "deepseek", label: "DeepSeek", protocol: "openai", baseUrl: "https://api.deepseek.com" },
  {
    id: "openrouter",
    label: "OpenRouter",
    protocol: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
  },
  { id: "ollama", label: "Ollama", protocol: "ollama", baseUrl: "http://localhost:11434" },
  { id: "custom", label: "Custom", protocol: "", baseUrl: "" },
];

// Which vendor a saved connection belongs to. Nothing stores a vendor: the
// presets only seed the form, so the endpoint is the only evidence left of who
// the user picked — we recover the vendor by matching the saved base URL back
// against PRESETS. The consequence is that editing a preset's endpoint (a proxy
// in front of OpenAI, say) makes the connection read as Custom, which is honest:
// from Coffer's side it is no longer the vendor's own endpoint.
//
// `custom` is returned with an empty label because the only label for it lives in
// i18n — the caller renders `settings.connections.customProvider`.
export function vendorOf(baseUrl: string): { id: string; label: string } {
  const wanted = normaliseEndpoint(baseUrl);
  const hit = PRESETS.find((p) => p.baseUrl !== "" && normaliseEndpoint(p.baseUrl) === wanted);
  return hit ? { id: hit.id, label: hit.label } : { id: "custom", label: "" };
}

// Endpoints differ only cosmetically between what a preset carries and what the
// user (or the backend) stored — case and a trailing slash carry no meaning here.
function normaliseEndpoint(url: string): string {
  return url.trim().toLowerCase().replace(/\/+$/, "");
}

// One display label per agent type, shared by every surface that RENDERS the
// effective compatible-agents set (the list table's chips, the detail page's
// configuration card). Nothing writes that set any more — it is derived from the
// resource's scope — so these labels are read-only display.
export const AGENT_LABEL_KEY: Record<AgentType, string> = {
  claude_code: "settings.connections.agentClaudeCode",
  codex: "settings.connections.agentCodex",
};
