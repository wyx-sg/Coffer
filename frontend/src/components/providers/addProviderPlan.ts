// src/components/providers/addProviderPlan.ts — what the Add dialog offers and sends, from what Test or detection found.
import type {
  LocalRuntimeFound,
  Protocol,
  ProviderCreate,
  ProviderModel,
} from "@/lib/api/providers";
import { secretRef, type SecretFieldValue } from "@/lib/secretValue";
import type { CandidateModel } from "./AddModelsStep";
import type { EndpointValues } from "./providerSchemas";

/** The wires a detected runtime serves to agents. */
export function localProtocolsOf(runtime: LocalRuntimeFound | null): Protocol[] {
  return (runtime?.runtime.wires ?? []).filter(
    (w): w is "anthropic" | "openai" => w === "anthropic" || w === "openai",
  );
}

/** A local runtime's models as candidates: text, with the window it serves. */
export function localCandidates(runtime: LocalRuntimeFound | null): CandidateModel[] {
  return (runtime?.models ?? []).map((m) => ({
    id: m.id,
    modality: "text",
    context_window: m.context_window,
    tools: m.tools,
  }));
}

/** How a request carries the key: a stored secret by its ref, a new one as its value (the daemon
 *  stores it when the provider is added). */
export function keyOf(secret: SecretFieldValue): { secret_ref: string } | { secret_value: string } {
  if (secret?.kind === "stored") {
    return { secret_ref: secret.name.includes("/") ? secret.name : secretRef(secret.name) };
  }
  return { secret_value: secret?.value ?? "" };
}

/** The `POST /providers` body. `selected` empty = every model offered. */
export function createBody(
  v: EndpointValues,
  runtime: LocalRuntimeFound | null,
  candidates: readonly CandidateModel[],
  selected: ReadonlySet<string>,
): ProviderCreate {
  const models: ProviderModel[] = candidates
    .filter((m) => selected.has(m.id))
    .map((m) => ({
      id: m.id,
      modality: m.modality,
      ...(m.context_window ? { context_window: m.context_window } : {}),
    }));
  const typed = v.baseUrl.trim();
  const body: ProviderCreate = {
    name: v.name.trim(),
    protocol: v.protocol,
    base_url: v.local ? (runtime?.base_url ?? typed) : typed,
  };
  if (!v.local) Object.assign(body, keyOf(v.secret));
  if (v.local && runtime) body.local_runtime = runtime.runtime;
  if (models.length > 0) body.models = models;
  return body;
}
