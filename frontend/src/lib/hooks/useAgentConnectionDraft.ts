// frontend/src/lib/hooks/useAgentConnectionDraft.ts — the draft → test → confirm
// state machine behind the agent's Model tab (spec provider-switching "Offer
// every connection operation on REST, CLI and web").
//
// Picking a provider, model, effort or tier is a DRAFT: nothing is PATCHed or
// activated until Confirm. A custom connection must pass a test for the CURRENT
// draft first (any change resets the result); the built-in login needs none.
// Confirm PATCHes the agent's binding, then activates the connection — the only
// step that writes native config — with `effort` and, for Claude Code,
// `tier_models` (an explicit null clears them). The built-in login writes no
// binding: nothing reads it there, so the tab shows the agent's own default
// model and its effort read-only.
//
// Model options: a connection with a CURATED set (`models` non-empty) IS the
// catalogue and is never introspected; an empty set means "no restriction" and
// the endpoint is introspected. Both are narrowed to modality `text` (spec
// provider-switching "Offer only text models to chat pickers"), and the staged
// model is seeded first so it never vanishes from the list. Effort levels come from what the connection records for the chosen model,
// else from the agent's own catalogue entry for that id.
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import { useToast } from "@/components/ui/toast";
import type { AgentOut, AgentPatch } from "@/lib/api/agents";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { modelIds, WIRE_BY_AGENT, type Provider } from "@/lib/api/providers";
import { agentsKey, providersKey } from "@/lib/api/queryKeys";
import { agentTypeLabel } from "@/lib/agents/display";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import { usePatchAgent } from "@/lib/hooks/useAgents";
import { useListProviderModels, useTestConnection } from "@/lib/hooks/useModelIntrospection";
import { useActivateProvider, useProviders, useUseBuiltinProvider } from "@/lib/hooks/useProviders";

// Radix forbids an empty value, so the "use built-in login" option is a token.
export const BUILTIN = "__builtin__";

export type Tier = "opus" | "sonnet" | "haiku" | "fable";
type TierModels = Partial<Record<Tier, string>>;
const BASE_TIERS: Tier[] = ["opus", "sonnet", "haiku"];

/** A connection to a model runtime on this machine: detected as one, or on loopback. */
function isLocal(conn: Provider | null): boolean {
  if (!conn) return false;
  if (conn.local_runtime) return true;
  try {
    const host = new URL(conn.base_url ?? "").hostname.replace(/^\[|\]$/g, "");
    return host === "localhost" || host === "127.0.0.1" || host === "::1";
  } catch {
    return false;
  }
}

/** The tiers a connection offers: Fable only when one of its models is a Fable. */
function tiersFor(models: string[]): Tier[] {
  return models.some((m) => m.toLowerCase().includes("fable"))
    ? [...BASE_TIERS, "fable"]
    : BASE_TIERS;
}

/** Coffer's prefill (spec provider-switching "Suggest a model for each Claude
 *  Code tier"): the model whose id names the tier, else the Model; a local
 *  runtime pins every tier to the Model. */
function suggestTiers(models: string[], model: string, local: boolean): TierModels {
  const out: TierModels = {};
  for (const tier of tiersFor(models)) {
    const match = local ? undefined : models.find((m) => m.toLowerCase().includes(tier));
    out[tier] = match ?? model;
  }
  return out;
}

const tiersKey = (tiers: TierModels) => JSON.stringify(Object.entries(tiers).sort());

export function useAgentConnectionDraft(agent: AgentOut) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const qc = useQueryClient();
  const wire = WIRE_BY_AGENT[agent.type];
  const providers = useProviders();
  const catalogue = useAgentModels(agent.type);
  const activate = useActivateProvider();
  const useBuiltin = useUseBuiltinProvider();
  const patchAgent = usePatchAgent();
  const list = useListProviderModels();
  const test = useTestConnection();

  const hasTiers = wire === "anthropic";
  // Offerable = routed to this agent type AND switched on (`compatible_agents`
  // is the configured reach and deliberately ignores `enabled`).
  const compatible = useMemo(
    () =>
      (providers.data ?? []).filter(
        (p) => p.enabled && (p.compatible_agents ?? []).includes(agent.type),
      ),
    [providers.data, agent.type],
  );
  const active = compatible.find((p) => p.is_active) ?? null;

  // APPLIED state. Tracked by uid: a renamed connection must stay selected.
  const appliedConn = active?.uid ?? BUILTIN;
  const appliedModel = active === null ? "" : (agent.model ?? "");
  const appliedEffort = agent.effort ?? null;
  const appliedTiersJson = tiersKey(hasTiers ? (agent.tier_models ?? {}) : {});
  const appliedTiers = useMemo<TierModels>(
    () => Object.fromEntries(JSON.parse(appliedTiersJson) as [Tier, string][]),
    [appliedTiersJson],
  );

  const [draftConn, setDraftConn] = useState(appliedConn);
  const [draftModel, setDraftModel] = useState(appliedModel);
  const [draftEffort, setDraftEffort] = useState<string | null>(appliedEffort);
  const [draftTiers, setDraftTiers] = useState<TierModels>(appliedTiers);
  const [fetched, setFetched] = useState<string[]>([]);

  const resetDraft = () => {
    setDraftConn(appliedConn);
    setDraftModel(appliedModel);
    setDraftEffort(appliedEffort);
    setDraftTiers(appliedTiers);
    setFetched([]);
    test.reset();
  };
  // Re-sync when the APPLIED state changes (load, confirm, an external switch);
  // a same-value refetch leaves an in-progress draft alone.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(resetDraft, [appliedConn, appliedModel, appliedEffort, appliedTiers]);

  const draftConnObj = compatible.find((p) => p.uid === draftConn) ?? null;
  const draftIsBuiltin = draftConn === BUILTIN;
  const local = isLocal(draftConnObj);

  // "Restricted" is asked of the WHOLE curated set; the options are its text
  // entries — a set curating only embeddings offers no chat model at all.
  const restricted = (draftConnObj?.models ?? []).length > 0;
  const models = useMemo(() => {
    const source = restricted ? modelIds(draftConnObj?.models ?? [], "text") : fetched;
    const out: string[] = [];
    for (const m of [draftModel, ...source]) if (m && !out.includes(m)) out.push(m);
    return out;
  }, [draftModel, fetched, draftConnObj, restricted]);

  const entries = catalogue.data ?? [];
  // The agent's own default is knowable only while the catalogue IS its own —
  // i.e. while the built-in login is what is applied.
  const builtinDefault = appliedConn === BUILTIN ? (entries[0] ?? null) : null;
  const curatedEntry = (draftConnObj?.models ?? []).find((m) => m.id === draftModel);
  const effortLevels = draftIsBuiltin
    ? (builtinDefault?.efforts ?? [])
    : (curatedEntry?.effort_levels ?? entries.find((m) => m.id === draftModel)?.efforts ?? []);

  const showTiers = hasTiers && !draftIsBuiltin;
  const tiers = tiersFor(models);
  const suggestion = useMemo(
    () => suggestTiers(models, draftModel, local),
    [models, draftModel, local],
  );

  const introspect = () => {
    if (!draftConnObj || restricted) return;
    list.mutate(
      {
        provider: draftConnObj.protocol,
        base_url: draftConnObj.base_url,
        secret_ref: draftConnObj.secret_ref,
      },
      { onSuccess: (r) => setFetched(modelIds(r.models, "text")) },
    );
  };

  // Staging a model resets its effort and tier prefill, and any earlier test.
  const stageModel = (m: string, pool: string[], onLocal: boolean) => {
    setDraftModel(m);
    setDraftEffort(null);
    setDraftTiers(hasTiers ? suggestTiers(pool, m, onLocal) : {});
    test.reset();
  };

  const pickConnection = (uid: string) => {
    setDraftConn(uid);
    setFetched([]);
    activate.reset();
    if (uid === BUILTIN) return stageModel("", [], false);
    const conn = compatible.find((p) => p.uid === uid);
    if (!conn) return;
    const connLocal = isLocal(conn);
    // Stage (never apply) a default model so there is something to test.
    if ((conn.models ?? []).length > 0) {
      const pinned = modelIds(conn.models ?? [], "text");
      return stageModel(pinned[0] ?? "", pinned, connLocal);
    }
    stageModel("", [], connLocal);
    list.mutate(
      { provider: conn.protocol, base_url: conn.base_url, secret_ref: conn.secret_ref },
      {
        onSuccess: (r) => {
          const ids = modelIds(r.models, "text");
          setFetched(ids);
          stageModel(ids[0] ?? "", ids, connLocal);
        },
      },
    );
  };

  const runTest = () => {
    if (!draftConnObj || !draftModel) return;
    test.mutate({
      provider: draftConnObj.protocol,
      model: draftModel,
      base_url: draftConnObj.base_url,
      secret_ref: draftConnObj.secret_ref,
    });
  };

  const switched = (target: string) =>
    toast.success(
      t("agents.modelTab.switchedToast", { agent: agentTypeLabel(agent.type), target }),
    );

  const confirm = () => {
    activate.reset();
    if (draftIsBuiltin) {
      useBuiltin.mutate(agent.type, {
        onSuccess: () => switched(t("agents.modelTab.builtinTarget")),
      });
      return;
    }
    const body: AgentPatch = { model: draftModel, effort: draftEffort };
    if (showTiers) body.tier_models = draftTiers;
    patchAgent.mutate(
      { uid: agent.uid, body },
      {
        onSuccess: () => activate.mutate(draftConn, { onSuccess: () => switched(draftModel) }),
        // usePatchAgent carries no toast of its own.
        onError: (e) => toast.error(translateApiError(t, e)),
      },
    );
  };

  // A 409 CONFIG_FILE_STALE keeps the draft; Reload refetches what the preview
  // was made from.
  const stale = activate.error instanceof ApiError && activate.error.code === "CONFIG_FILE_STALE";
  const reload = () => {
    activate.reset();
    void qc.invalidateQueries({ queryKey: providersKey });
    void qc.invalidateQueries({ queryKey: agentsKey });
  };
  const error = stale ? null : (activate.error ?? patchAgent.error ?? useBuiltin.error ?? null);

  const dirty =
    draftConn !== appliedConn ||
    draftModel !== appliedModel ||
    (!draftIsBuiltin && draftEffort !== appliedEffort) ||
    (showTiers && tiersKey(draftTiers) !== appliedTiersJson);
  const canConfirm = dirty && (draftIsBuiltin || (!!draftModel && test.data?.ok === true));
  const busy = activate.isPending || patchAgent.isPending || useBuiltin.isPending;

  return {
    wire,
    compatible,
    appliedConn,
    draftConn,
    draftConnObj,
    draftIsBuiltin,
    draftModel,
    models,
    builtinDefault,
    local,
    effortLevels,
    draftEffort,
    showTiers,
    tiers,
    draftTiers,
    dirty,
    canConfirm,
    busy,
    loading: providers.isPending,
    stale,
    error,
    testPending: test.isPending,
    testResult: test.data ?? null,
    introspect,
    pickConnection,
    pickModel: (m: string) => stageModel(m, models, local),
    pickEffort: (e: string | null) => setDraftEffort(e),
    pickTier: (tier: Tier, m: string) => setDraftTiers((cur) => ({ ...cur, [tier]: m })),
    resetTiers: () => setDraftTiers(suggestion),
    runTest,
    discard: () => {
      resetDraft();
      activate.reset();
      patchAgent.reset();
      useBuiltin.reset();
    },
    confirm,
    reload,
  };
}

export type ConnectionDraft = ReturnType<typeof useAgentConnectionDraft>;
