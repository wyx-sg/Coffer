// frontend/src/lib/hooks/useModelIntrospection.ts
//
// Provider introspection (spec 008/006): list a provider's models + test a
// connection, so the model forms offer a fetched dropdown (with manual
// fallback) and a Test button — DevPilot-style. Hand-written fetch, mirroring
// useEmbeddingConfig.
import { useMutation } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

export interface ProviderProbe {
  provider: string;
  model?: string;
  base_url?: string | null;
  credential_ref?: string | null;
}

export interface TestResult {
  ok: boolean;
  message: string;
  detail?: Record<string, unknown>;
}

function headers(): HeadersInit {
  return {
    "X-Coffer-Token": getCofferToken() ?? "",
    "X-Coffer-Actor": "ui",
    "Content-Type": "application/json",
  };
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${getCofferBaseUrl()}${path}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiError(
      data?.error?.code ?? "INTERNAL_ERROR",
      data?.error?.message ?? `request failed: ${r.status}`,
    );
  }
  return (await r.json()) as T;
}

/** List a provider's models. Empty list + message → user types manually. */
export function useListProviderModels() {
  return useMutation({
    mutationFn: (p: ProviderProbe) =>
      post<{ models: string[]; message: string }>("/models/list-models", {
        provider: p.provider,
        base_url: p.base_url ?? null,
        credential_ref: p.credential_ref ?? null,
      }),
  });
}

/** Probe a chat provider with a minimal request. */
export function useTestConnection() {
  return useMutation({
    mutationFn: (p: ProviderProbe) => post<TestResult>("/models/test-connection", p),
  });
}

/** Probe an embedding provider; success reports the vector dimension. */
export function useTestEmbedding() {
  return useMutation({
    mutationFn: (p: ProviderProbe) => post<TestResult>("/embedding/test", p),
  });
}
