// frontend/src/lib/api/models.ts — typed fetch helpers for /api/v1/models/*
// Hand-written wire types matching specs/008-agent-chat/contracts/api.openapi.yaml
// and backend/coffer/surfaces/http/chat/schemas.py.

import { getCofferBaseUrl, getCofferToken } from "../auth";
import { ApiError } from "./errors";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ModelProvider = "anthropic" | "openai" | "ollama";

export interface Model {
  id: string;
  display_name: string;
  provider: ModelProvider;
  model: string;
  credential_ref?: string | null;
  base_url?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelListOut {
  models: Model[];
}

export interface ModelCreate {
  display_name: string;
  provider: ModelProvider;
  model: string;
  credential_ref?: string | null;
  base_url?: string | null;
  is_default?: boolean;
}

export interface ModelPatch {
  display_name?: string | null;
  model?: string | null;
  credential_ref?: string | null;
  base_url?: string | null;
  is_default?: boolean | null;
}

// ---------------------------------------------------------------------------
// Internal fetch helper
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// API object
// ---------------------------------------------------------------------------

export const modelsApi = {
  list: () => call<ModelListOut>("GET", "/models"),

  create: (body: ModelCreate) => call<Model>("POST", "/models", body),

  update: (id: string, body: ModelPatch) =>
    call<Model>("PATCH", `/models/${id}`, body),

  remove: (id: string) => call<void>("DELETE", `/models/${id}`),
};
