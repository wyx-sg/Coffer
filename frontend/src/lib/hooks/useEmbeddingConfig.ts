// frontend/src/lib/hooks/useEmbeddingConfig.ts
//
// The single GLOBAL embedding configuration (no longer per knowledge base /
// memory store). GET/PUT /api/v1/embedding/config. Hand-written fetch (the
// generated client only covers spec 001), mirroring the kb/memory api helpers.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";

export interface EmbeddingConfigOut {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  base_url: string | null;
  credential_ref: string | null;
  dimensions: number;
  updated_at: string | null;
}

export interface EmbeddingConfigUpdate {
  enabled: boolean;
  provider: string | null;
  model: string | null;
  base_url: string | null;
  credential_ref: string | null;
  dimensions: number;
}

function headers(extra: HeadersInit = {}): HeadersInit {
  return { "X-Coffer-Token": getCofferToken() ?? "", "X-Coffer-Actor": "ui", ...extra };
}

async function checkOk(r: Response): Promise<Response> {
  if (!r.ok) {
    const data = (await r.json().catch(() => null)) as {
      error?: { code?: string; message?: string };
    } | null;
    throw new ApiError(
      data?.error?.code ?? "INTERNAL_ERROR",
      data?.error?.message ?? `request failed: ${r.status}`,
    );
  }
  return r;
}

export async function getEmbeddingConfig(): Promise<EmbeddingConfigOut> {
  const r = await fetch(`${getCofferBaseUrl()}/embedding/config`, { headers: headers() });
  await checkOk(r);
  return (await r.json()) as EmbeddingConfigOut;
}

export async function updateEmbeddingConfig(
  body: EmbeddingConfigUpdate,
): Promise<EmbeddingConfigOut> {
  const r = await fetch(`${getCofferBaseUrl()}/embedding/config`, {
    method: "PUT",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await checkOk(r);
  return (await r.json()) as EmbeddingConfigOut;
}

export function useEmbeddingConfig() {
  return useQuery({ queryKey: ["embedding-config"], queryFn: getEmbeddingConfig });
}

export function useUpdateEmbeddingConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: updateEmbeddingConfig,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["embedding-config"] }),
  });
}
