// components/settings/connectionPresets.ts — provider presets for the add-
// connection form, plus the default agent-compatibility per wire. A preset fills
// the endpoint + protocol; the user can still re-target which agents it projects
// into via the compatible-agents checkboxes (e.g. an openai gateway → Claude Code).
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

// The agents a connection projects into BY DEFAULT, mirroring the backend
// (`_DEFAULT_COMPATIBLE`). The form pre-fills the checkboxes from this. Every
// wire offers both agents: the protocol decides model introspection and whether
// a key is needed, not who may be driven by the endpoint (an openai gateway
// driving Claude Code is a first-class case), so the default is the widest set
// and the user narrows it. ollama is the exception — internal-only, it projects
// into no agent.
export function defaultCompatibleAgents(protocol: Protocol | ""): AgentType[] {
  switch (protocol) {
    case "ollama":
      return [];
    default:
      return ["claude_code", "codex"];
  }
}

// The agents a user can tick a connection as compatible with.
export const SELECTABLE_AGENTS: AgentType[] = ["claude_code", "codex"];

// One display label per agent type, shared by every surface that renders the
// compatible-agents set (the form's checkboxes, the list table's chips, the
// detail page's configuration card).
export const AGENT_LABEL_KEY: Record<AgentType, string> = {
  claude_code: "settings.connections.agentClaudeCode",
  codex: "settings.connections.agentCodex",
};
