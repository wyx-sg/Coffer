// src/lib/hooks/useModelTest.ts — the Test button beside a model picker (the speech-to-text picker
// in Settings › General, an agent's Overview › Model).
//
// Two probes, because the pickers run different kinds of model (spec
// internal-engine "Show the speech-to-text pair in Settings › General"):
//
//   • `chat` (an agent's model) — one `POST /api/v1/models/test-connection`, a
//     minimal chat request to the chosen connection and model, on the wire
//     the agent speaks (`probeProtocol`).
//   • `list` (speech to text) — one `POST /api/v1/models/list-models` for the
//     chosen connection. A chat probe would fail on a speech model even on a
//     healthy endpoint, so this asks the endpoint what it serves instead: it
//     passes when the listing names the chosen model, and fails when the
//     endpoint answered without it or could not be reached. An endpoint that
//     answers but lists nothing is reachable and unverified, not failing.
//
// The result belongs to the PAIR it was run on: switching provider or model
// drops it, so a pass on the old pair never reads as the new one answering. A
// test only reads — it never writes the pair, whatever it finds.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { Provider } from "@/lib/api/providers";
import { translateApiError } from "@/lib/api/errors";
import { useListProviderModels, useTestConnection } from "@/lib/hooks/useModelIntrospection";
import { probeProtocol } from "@/lib/hooks/useModelSwitchTest";

export type PairTestMode = "chat" | "list";

/** @ui-only derived view; never crosses the wire. */
export interface PairTestResult {
  /** `reachable`: the endpoint answered but lists no models to check against. */
  outcome: "ok" | "reachable" | "failed";
  /** The reason on failure; empty otherwise. */
  message: string;
}

export function useModelPairTest(
  connection: Provider | null,
  model: string,
  mode: PairTestMode = "chat",
  agentType?: string,
) {
  const { t } = useTranslation();
  const chat = useTestConnection();
  const list = useListProviderModels();
  const pair = connection && model ? `${connection.uid}\u0000${model}` : null;
  const [result, setResult] = useState<{ pair: string; outcome: PairTestResult } | null>(null);

  const run = () => {
    if (!connection || !model || pair === null) return;
    const settle = (outcome: PairTestResult) => setResult({ pair, outcome });
    // Rendered inline as the failing state, not toasted: the row is where the
    // reader is looking, and the error is the answer to the button.
    const onError = (error: unknown) =>
      settle({ outcome: "failed", message: translateApiError(t, error) });
    const probe = {
      provider: probeProtocol(connection, agentType),
      base_url: connection.base_url,
      secret_ref: connection.secret_ref,
    };
    if (mode === "chat") {
      chat.mutate(
        { ...probe, model },
        {
          onSuccess: (r) =>
            settle(
              r.ok ? { outcome: "ok", message: "" } : { outcome: "failed", message: r.message },
            ),
          onError,
        },
      );
      return;
    }
    list.mutate(probe, {
      onSuccess: (r) => {
        if (r.models.some((m) => m.id === model)) settle({ outcome: "ok", message: "" });
        else if (r.models.length > 0)
          settle({
            outcome: "failed",
            message: t("settings.cofferModel.notListed", { model }),
          });
        // The route degrades a failed listing to an empty list plus its reason;
        // `reachable` says which of the two an empty answer is.
        else if (r.reachable) settle({ outcome: "reachable", message: "" });
        else
          settle({ outcome: "failed", message: r.message || t("settings.cofferModel.noAnswer") });
      },
      onError,
    });
  };

  return {
    result: result !== null && result.pair === pair ? result.outcome : null,
    run,
    isPending: mode === "chat" ? chat.isPending : list.isPending,
  };
}
