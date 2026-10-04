// frontend/src/lib/hooks/useModelSwitchTest.ts — the connection test behind the Change model dialog
// (spec provider-switching "Review a model change before writing it").
//
// Naming a Coffer provider and a model starts one chat probe
// (`POST /api/v1/models/test-connection`, the call Overview › Model › Test
// makes) once the draft has rested for a moment. Changing the pair cancels the
// run in flight, and a result belongs only to the pair it was run on, so a
// pass on the old pair never unlocks the new one.
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { translateApiError } from "@/lib/api/errors";
import { modelProbeApi, type Provider } from "@/lib/api/providers";

/** One run per pair and endpoint (kept here: queryKeys.ts is at its size limit). */
const modelSwitchTestKey = (pair: string | null, baseUrl?: string | null, ref?: string | null) =>
  ["model-switch-test", pair, baseUrl, ref] as const;

const DEBOUNCE_MS = 400;

/** @ui-only derived view; never crosses the wire. */
export type SwitchTestStatus =
  | { state: "none" }
  | { state: "testing" }
  | { state: "passed"; ms: number }
  | { state: "failed"; message: string };

interface Outcome {
  ok: boolean;
  message: string;
  ms: number;
}

export function useModelSwitchTest(connection: Provider | null, model: string) {
  const { t } = useTranslation();
  const pair = connection && model ? `${connection.uid}\u0000${model}` : null;
  const [settled, setSettled] = useState<string | null>(pair);

  // Debounce: the probe waits until the draft stops changing.
  useEffect(() => {
    if (pair === settled) return;
    const id = setTimeout(() => setSettled(pair), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [pair, settled]);

  const query = useQuery<Outcome>({
    // The pair AND the endpoint it names: editing the connection retests.
    queryKey: modelSwitchTestKey(settled, connection?.base_url, connection?.secret_ref),
    enabled: settled !== null && settled === pair && !!connection,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => {
      const started = performance.now();
      const ms = () => Math.round(performance.now() - started);
      try {
        const r = await modelProbeApi.test(
          {
            provider: connection!.protocol,
            model,
            base_url: connection!.base_url,
            secret_ref: connection!.secret_ref,
          },
          signal,
        );
        return { ok: r.ok, message: r.message, ms: ms() };
      } catch (error) {
        if (signal.aborted) throw error;
        return { ok: false, message: translateApiError(t, error), ms: ms() };
      }
    },
  });

  let status: SwitchTestStatus;
  if (pair === null) status = { state: "none" };
  else if (settled !== pair || query.isFetching || !query.data) status = { state: "testing" };
  else if (query.data.ok) status = { state: "passed", ms: query.data.ms };
  else status = { state: "failed", message: query.data.message };

  return { status, retry: () => void query.refetch() };
}
