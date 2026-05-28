// frontend/src/lib/api/agents.ts — typed fetch helpers for /api/v1/agents/*
// Until openapi codegen merges specs 003/004, we hand-write the wire types
// to match `specs/004-agent-registry/contracts/api.openapi.yaml`.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

export type AgentType = "claude_code" | "claude_desktop" | "cursor" | "codex_cli";

export interface AgentOut {
  name: string;
  type: AgentType;
  skill_dir: string;
  skill_dir_override: string | null;
  auto_detected: boolean;
  enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentListOut {
  items: AgentOut[];
}

export interface AgentCreate {
  type: AgentType;
  name: string;
  skill_dir?: string | null;
  description?: string | null;
}

export interface AgentPatch {
  skill_dir?: string | null;
  description?: string | null;
  enabled?: boolean | null;
}

export interface AgentDetectOut {
  registered: AgentOut[];
}

async function call<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": getCofferToken() ?? "",
      "X-Coffer-Actor": "ui",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 204) {
    return undefined as unknown as T;
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    const err = data?.error;
    throw new ApiError(
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `request failed: ${r.status}`,
    );
  }
  return data as T;
}

export const agentsApi = {
  list: () => call<AgentListOut>("GET", "/agents"),
  register: (body: AgentCreate) => call<AgentOut>("POST", "/agents", body),
  get: (name: string) => call<AgentOut>("GET", `/agents/${name}`),
  patch: (name: string, body: AgentPatch) => call<AgentOut>("PATCH", `/agents/${name}`, body),
  remove: (name: string) => call<void>("DELETE", `/agents/${name}`),
  detect: () => call<AgentDetectOut>("POST", "/agents/detect"),
};
