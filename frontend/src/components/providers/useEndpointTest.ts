// src/components/providers/useEndpointTest.ts — a dialog's Test: list the endpoint's models, timed, and classify the answer.
//
// The Add, Edit and Replace-key dialogs test before anything is saved, with
// the typed (unsaved) key inline. `POST /models/list-models` answers 200 even
// when the endpoint refuses, so the verdict is read from the answer (see
// lib/providers/probeStatus.ts). The latency is measured here, around the
// request — it includes the daemon's hop, which is what the user waits for.
import { useState } from "react";

import type { ProviderModel } from "@/lib/api/providers";
import { translateApiError } from "@/lib/api/errors";
import { type ProviderProbe, useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { authStatusOf, isAuthFailure, probeFailed } from "@/lib/providers/probeStatus";
import type { TFunction } from "i18next";

export type EndpointTestResult =
  | { kind: "ok"; ms: number; models: ProviderModel[] }
  | { kind: "rejected"; status: string | null; message: string }
  | { kind: "failed"; message: string };

export function useEndpointTest(t: TFunction) {
  const list = useListProviderModels();
  const [result, setResult] = useState<EndpointTestResult | null>(null);

  const run = async (probe: ProviderProbe): Promise<EndpointTestResult> => {
    setResult(null);
    const started = performance.now();
    let next: EndpointTestResult;
    try {
      const data = await list.mutateAsync(probe);
      const ms = Math.max(1, Math.round(performance.now() - started));
      if (!probeFailed(data, null)) next = { kind: "ok", ms, models: data.models };
      else if (isAuthFailure(data.message))
        next = { kind: "rejected", status: authStatusOf(data.message), message: data.message };
      else next = { kind: "failed", message: data.message };
    } catch (e) {
      // Rendered inline as the test's verdict, so no toast.
      next = { kind: "failed", message: translateApiError(t, e) };
    }
    setResult(next);
    return next;
  };

  return { run, result, reset: () => setResult(null), isPending: list.isPending };
}
