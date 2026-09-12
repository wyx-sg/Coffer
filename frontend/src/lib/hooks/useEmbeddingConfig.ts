// frontend/src/lib/hooks/useEmbeddingConfig.ts
//
// The single GLOBAL embedding configuration (no longer per knowledge base /
// memory store). GET/PUT /api/v1/embedding/config. Hand-written fetch (the
// generated client only covers spec mcp-gateway), mirroring the kb/memory api helpers.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCofferBaseUrl, getCofferToken } from "@/lib/auth";
import { ApiError } from "@/lib/api/errors";
import { modelIds, type Provider } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";

/**
 * The installation-wide embedding setting (knowledge FR-077): it NAMES a
 * connection rather than restating one. `connection` is the name of a configured
 * model provider and `model` one of the `embedding`-modality models it offers —
 * the same "pick a provider, then pick a model" shape the internal engine has.
 * The wire, base URL and API key live on that connection and are resolved from
 * it at use time, so they are neither sent nor returned here, and there is no
 * `secret_value`: the embedding settings own no key of their own.
 */
export interface EmbeddingConfigOut {
  enabled: boolean;
  connection: string | null;
  model: string | null;
  dimensions: number;
  default_chunk_size: number;
  default_chunk_overlap: number;
  updated_at: string | null;
}

export interface EmbeddingConfigUpdate {
  enabled: boolean;
  connection: string | null;
  model: string | null;
  dimensions: number;
  default_chunk_size: number;
  default_chunk_overlap: number;
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

/**
 * The embedding models a connection offers to the global embedding setting.
 *
 * A connection that curates models IS the catalogue — its `embedding`-modality
 * entries and nothing else, so a chat model can never be picked as the
 * embedder, and a connection that curates only chat models offers nothing here
 * (which is exactly what the daemon refuses to save). A connection curating
 * NOTHING means "no restriction", so the endpoint is probed and its own list,
 * narrowed the same way, is what the picker shows.
 */
export function useEmbeddingModels(connection: Provider | null) {
  const list = useListProviderModels();
  const [fetched, setFetched] = useState<string[]>([]);
  const curated = connection?.models ?? [];
  const restricted = curated.length > 0;

  // `stale` guards against a slower earlier probe landing after a newer one when
  // the connection is switched rapidly.
  useEffect(() => {
    if (!connection || restricted) {
      setFetched([]);
      return;
    }
    let stale = false;
    list.mutate(
      {
        provider: connection.protocol,
        base_url: connection.base_url,
        credential_ref: connection.credential_ref,
      },
      {
        onSuccess: (r) => {
          if (!stale) setFetched(modelIds(r.models, "embedding"));
        },
      },
    );
    return () => {
      stale = true;
    };
    // list identity is stable across renders; re-probe only on connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection?.name, connection?.base_url, connection?.credential_ref, restricted]);

  return {
    options: restricted ? modelIds(curated, "embedding") : fetched,
    /** True while the endpoint is being probed (unrestricted connections only). */
    probing: list.isPending,
  };
}
