// frontend/src/lib/hooks/useConnectionModelOptions.ts
// The model ids one connection offers for ONE modality — the list behind every
// "which model?" dropdown in Settings → Coffer's model.
//
// Two sources, in this order: a connection's CURATED set when it has one — that
// IS its catalogue, and an embedding entry is no more a chat model here than in
// an agent's picker — and otherwise the endpoint's own list, probed once per
// connection (spec provider-switching "Curate the models a connection offers").
// Both are narrowed to the
// modality the caller needs, because one base URL and key answer for chat,
// embeddings, images and speech alike.
//
// It lives here rather than inside the engine card because the speech-to-text
// card asks the same question of a different connection and a different
// modality; two copies of the probe would be two chances for them to drift.
import { useEffect, useState } from "react";

import { modelIds, type Modality, type Provider } from "@/lib/api/providers";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";

/**
 * @param connection the connection whose models are wanted, or null for none
 * @param modality which KIND of model the caller needs (`text`, `audio`, …)
 * @param current the saved id, kept at the head of the list even when the
 *   endpoint cannot list it — otherwise a working setting would read as unset
 */
export function useConnectionModelOptions(
  connection: Provider | null,
  modality: Modality,
  current: string,
): string[] {
  const listModels = useListProviderModels();
  const [fetched, setFetched] = useState<string[]>([]);

  const curated = connection?.models ?? [];
  const restricted = curated.length > 0;

  // A curated connection needs no probe. `stale` guards against a slower earlier
  // request landing after a newer one when the connection is switched rapidly.
  useEffect(() => {
    if (!connection || restricted) {
      setFetched([]);
      return;
    }
    let stale = false;
    listModels.mutate(
      {
        provider: connection.protocol,
        base_url: connection.base_url,
        credential_ref: connection.credential_ref,
      },
      {
        onSuccess: (r) => {
          if (!stale) setFetched(modelIds(r.models, modality));
        },
      },
    );
    return () => {
      stale = true;
    };
    // listModels identity is stable across renders; re-fetch only on connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection?.name, connection?.base_url, connection?.credential_ref, restricted, modality]);

  const models = restricted ? modelIds(curated, modality) : fetched;
  return current && !models.includes(current) ? [current, ...models] : models;
}
