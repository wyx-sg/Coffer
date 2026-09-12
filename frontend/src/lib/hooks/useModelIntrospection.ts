// frontend/src/lib/hooks/useModelIntrospection.ts
//
// Provider introspection (specs channels and knowledge): list a provider's models + test a
// connection, so the model forms offer a fetched dropdown (with manual
// fallback) and a Test button — DevPilot-style. Hand-written fetch, mirroring
// useEmbeddingConfig.
import { useMutation, useQuery } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

export interface ProviderProbe {
  provider: string;
  model?: string;
  base_url?: string | null;
  credential_ref?: string | null;
  /** Inline, not-yet-saved key so the dialog can test/fetch before save. */
  secret_value?: string | null;
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
        secret_value: p.secret_value ?? null,
      }),
  });
}

/** The model ids an endpoint itself serves, as a QUERY rather than the mutation
 *  above: a surface whose whole job is to show that list (the connection detail
 *  page) should have it on open, not behind a button, and a query is what gives
 *  it the loading / error / refetch states that makes a failed probe visible and
 *  retryable.
 *
 *  The key deliberately does NOT extend ``["providers", name]``: every
 *  connection mutation invalidates that subtree, so ticking one model on would
 *  re-probe the remote endpoint — a network round trip per click. This list
 *  changes when the ENDPOINT changes, not when our curation does.
 *
 *  `retry: false` because a wrong key or an unreachable endpoint is a real
 *  answer the user must see, not a blip worth three silent attempts. */
export const endpointModelsKey = (name: string) => ["endpointModels", name] as const;

export function useEndpointModels(name: string, probe: ProviderProbe) {
  return useQuery({
    queryKey: endpointModelsKey(name),
    queryFn: () =>
      post<{ models: string[]; message: string }>("/models/list-models", {
        provider: probe.provider,
        base_url: probe.base_url ?? null,
        credential_ref: probe.credential_ref ?? null,
        secret_value: probe.secret_value ?? null,
      }),
    enabled: name !== "",
    retry: false,
    refetchOnWindowFocus: false,
    // The tab this renders in unmounts when the user switches away, so without a
    // stale window every flick back to it would re-probe the vendor. Once per
    // visit to the page is what "listed when you open it" means; the Retry
    // button is there for when the user wants it asked again.
    staleTime: 5 * 60 * 1000,
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

/** Detect an endpoint's wire protocol so the dialog needs no manual type pick.
 * Returns "anthropic" | "openai" | "ollama" | "unknown" (unknown ⇒ user picks). */
export function useDetectProtocol() {
  return useMutation({
    mutationFn: (p: { base_url?: string | null; secret_value?: string | null }) =>
      post<{ protocol: string }>("/models/detect-protocol", {
        base_url: p.base_url ?? null,
        secret_value: p.secret_value ?? null,
      }),
  });
}
