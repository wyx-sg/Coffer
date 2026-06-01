// frontend/src/lib/api/builtinAgents.ts — typed wrappers around the generic
// kind-agnostic resource endpoints for the `builtin_agent` kind (spec 008 US8).
// Coffer's own LLM agent is just a resource of kind `builtin_agent`; CRUD on it
// rides the same `/resources` routes every other kind uses (no dedicated path).
import { getApiClient } from "@/lib/api/client";
import { ApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";

export const BUILTIN_AGENT_KIND = "builtin_agent" as const;

/**
 * Validated server-side config for a built-in agent (`extra=forbid`). Mirrors
 * the backend `BuiltinAgentConfig` Pydantic schema; PATCH sends the full object.
 */
export interface BuiltinAgentConfig {
  /** Provider-qualified model, e.g. `anthropic:claude-sonnet-4-6`. Required. */
  model: string;
  system_prompt?: string;
  /** Sampling temperature 0..2. */
  temperature?: number;
  /** Max tokens (>0). */
  max_tokens?: number;
  /** Keychain ref for the provider API key. */
  credential_ref?: string;
  /** Give the agent Coffer's MCP gateway tools (default true). */
  use_gateway?: boolean;
  /** Tool-name glob patterns requiring confirmation, e.g. `*delete*`. */
  confirm_tools?: string[];
}

type ResourceOut = components["schemas"]["ResourceOut"];

/** A built-in agent: a {@link ResourceOut} with a typed `config`. */
export interface BuiltinAgentOut extends Omit<ResourceOut, "config"> {
  config: BuiltinAgentConfig;
}

export interface BuiltinAgentCreate {
  name: string;
  config: BuiltinAgentConfig;
  description?: string | null;
}

function asBuiltinAgent(r: ResourceOut): BuiltinAgentOut {
  return { ...r, config: r.config as unknown as BuiltinAgentConfig };
}

export const builtinAgentsApi = {
  list: async (): Promise<BuiltinAgentOut[]> => {
    const { data, error } = await getApiClient().GET("/resources", {
      params: { query: { kind: BUILTIN_AGENT_KIND } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to list built-in agents");
    return (data?.resources ?? []).map(asBuiltinAgent);
  },

  get: async (name: string): Promise<BuiltinAgentOut> => {
    const { data, error } = await getApiClient().GET("/resources/{kind}/{name}", {
      params: { path: { kind: BUILTIN_AGENT_KIND, name } },
    });
    if (error) throwApiError(error, "RESOURCE_NOT_FOUND", "built-in agent not found");
    if (!data) throw new ApiError("RESOURCE_NOT_FOUND", "empty built-in agent response");
    return asBuiltinAgent(data);
  },

  create: async (body: BuiltinAgentCreate): Promise<BuiltinAgentOut> => {
    const { data, error } = await getApiClient().POST("/resources", {
      body: {
        kind: BUILTIN_AGENT_KIND,
        name: body.name,
        config: body.config as unknown as Record<string, unknown>,
        ...(body.description != null ? { description: body.description } : {}),
      },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to create built-in agent");
    if (!data) throw new ApiError("INTERNAL_ERROR", "empty built-in agent response");
    return asBuiltinAgent(data);
  },

  // Edit config — the server replaces the whole config object, so callers send
  // the full merged config (not a diff).
  patch: async (name: string, config: BuiltinAgentConfig): Promise<BuiltinAgentOut> => {
    const { data, error } = await getApiClient().PATCH("/resources/{kind}/{name}", {
      params: { path: { kind: BUILTIN_AGENT_KIND, name } },
      body: { config: config as unknown as Record<string, unknown> },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to update built-in agent");
    if (!data) throw new ApiError("INTERNAL_ERROR", "empty built-in agent response");
    return asBuiltinAgent(data);
  },

  // May 409 with CANNOT_DELETE_LAST_BUILTIN_AGENT — the last one can't be deleted.
  remove: async (name: string): Promise<void> => {
    const { error } = await getApiClient().DELETE("/resources/{kind}/{name}", {
      params: { path: { kind: BUILTIN_AGENT_KIND, name } },
    });
    if (error) throwApiError(error, "INTERNAL_ERROR", "failed to delete built-in agent");
  },
};
