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
    id: "moonshot",
    label: "Moonshot (Kimi)",
    protocol: "openai",
    baseUrl: "https://api.moonshot.cn/v1",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    protocol: "openai",
    baseUrl: "https://openrouter.ai/api/v1",
  },
  { id: "ollama", label: "Ollama", protocol: "ollama", baseUrl: "http://localhost:11434" },
  { id: "custom", label: "Custom", protocol: "", baseUrl: "" },
];

// The agents a connection projects into BY DEFAULT, mirroring the backend
// (`_DEFAULT_COMPATIBLE`). The form pre-fills the checkboxes from this; ollama is
// internal-only (projects into no agent). openclaw speaks BOTH wires (its
// provider `api` field takes openai-completions AND anthropic-messages,
// ADR-043), so it defaults into both.
export function defaultCompatibleAgents(protocol: Protocol | ""): AgentType[] {
  switch (protocol) {
    case "anthropic":
      return ["claude_code", "openclaw"];
    case "openai":
      return ["codex", "opencode", "hermes", "openclaw"];
    case "unknown":
    case "": // custom, before a wire is picked
      return ["claude_code", "codex", "opencode", "hermes", "openclaw"];
    default: // ollama
      return [];
  }
}

// The agents a user can tick a connection as compatible with.
export const SELECTABLE_AGENTS: AgentType[] = [
  "claude_code",
  "codex",
  "opencode",
  "hermes",
  "openclaw",
];

// Agents that can never consume a connection, with the i18n key stating why —
// shown as a disabled checkbox + reason rather than silently omitted (ADR-042:
// an absent facet is surfaced, not hidden). cursor-agent exposes no base-URL
// flag or endpoint config key; it is locked to Cursor's own backend.
export const UNPROJECTABLE_AGENTS: { type: AgentType; reasonKey: string }[] = [
  { type: "cursor", reasonKey: "settings.connections.agentCursorUnprojectable" },
];
