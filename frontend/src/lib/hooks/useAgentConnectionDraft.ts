// frontend/src/lib/hooks/useAgentConnectionDraft.ts — the draft behind the agent's Change model dialog
// (spec provider-switching "Offer every connection operation over REST and in the web UI").
//
// Picking a provider, model or tier is a DRAFT: nothing is written
// until the user has reviewed the change (`useModelSwitch`). The hook holds the
// draft, derives what the form offers, and builds the request the review and
// the apply both send.
//
// Model options: a connection with a CURATED set (`models` non-empty) IS the
// catalogue and is never introspected; an empty set means "no restriction" and
// the endpoint is introspected. Both are narrowed to modality `text` (spec
// provider-switching "Offer only text models to chat pickers"), and the staged
// model is seeded first so it never vanishes from the list. The built-in login writes nothing: no
// model or tiers, so the dialog shows only the provider.
import { useEffect, useMemo, useState } from "react";

import type { AgentOut } from "@/lib/api/agents";
import type { ModelSwitchIn } from "@/lib/api/modelSwitch";
import { modelIds, WIRE_BY_AGENT } from "@/lib/api/providers";
import { activeProviderFor } from "@/lib/providers/usedBy";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useProviders } from "@/lib/hooks/useProviders";
import {
  BUILTIN,
  isLocal,
  suggestTiers,
  tiersFor,
  tiersKey,
  type Tier,
  type TierModels,
} from "@/lib/agents/connectionDraft";

export { BUILTIN, type Tier } from "@/lib/agents/connectionDraft";

export function useAgentConnectionDraft(agent: AgentOut) {
  const wire = WIRE_BY_AGENT[agent.type];
  const providers = useProviders();
  const list = useListProviderModels();
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
  // The agent's record names its connection; a pointer that no longer resolves
  // (deleted, switched off, out of scope) reads as the built-in login.
  const active = activeProviderFor(agent, providers.data ?? []);

  // APPLIED state. Tracked by uid: a renamed connection must stay selected.
  const appliedConn = active?.uid ?? BUILTIN;
  const appliedModel = active === null ? "" : (agent.model ?? "");
  const appliedTiers: TierModels = hasTiers ? ((agent.tier_models ?? {}) as TierModels) : {};
  const appliedTiersJson = tiersKey(appliedTiers);

  const [draftConn, setDraftConn] = useState(appliedConn);
  const [draftModel, setDraftModel] = useState(appliedModel);
  const [draftTiers, setDraftTiers] = useState<TierModels>(appliedTiers);
  const [fetched, setFetched] = useState<string[]>([]);
  // The draft has been reset to the applied state. Until then it holds the
  // pre-load guess, which would read as a change for one render.
  const [synced, setSynced] = useState(false);

  // The draft starts from what is applied, which is known once providers load.
  const loaded = !providers.isPending;
  useEffect(() => {
    if (!loaded) return;
    setDraftConn(appliedConn);
    setDraftModel(appliedModel);
    setDraftTiers(appliedTiers);
    setSynced(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when the applied state arrives
  }, [loaded]);

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

  // Staging a model resets its tier prefill.
  const stageModel = (m: string, pool: string[], onLocal: boolean) => {
    setDraftModel(m);
    setDraftTiers(hasTiers ? suggestTiers(pool, m, onLocal) : {});
  };

  const pickConnection = (uid: string) => {
    setDraftConn(uid);
    setFetched([]);
    if (uid === BUILTIN) return stageModel("", [], false);
    const conn = compatible.find((p) => p.uid === uid);
    if (!conn) return;
    const connLocal = isLocal(conn);
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

  const dirty =
    draftConn !== appliedConn ||
    draftModel !== appliedModel ||
    (showTiers && tiersKey(draftTiers) !== appliedTiersJson);
  // A model is needed on a provider; Review is for something to change.
  const canReview = dirty && (draftIsBuiltin || !!draftModel);

  /** What the review and the apply send. */
  const request: ModelSwitchIn = {
    agent_type: agent.type,
    connection_uid: draftIsBuiltin ? null : draftConn,
    model: draftIsBuiltin ? null : draftModel,
    tier_models: showTiers ? (draftTiers as Record<string, string>) : null,
  };

  return {
    compatible,
    appliedConn,
    draftConn,
    draftConnObj,
    draftIsBuiltin,
    draftModel,
    models,
    local,
    showTiers,
    tiers,
    draftTiers,
    tiersAreSuggested: tiersKey(draftTiers) === tiersKey(suggestion),
    loading: providers.isPending || !synced,
    dirty,
    canReview,
    request,
    introspect,
    pickConnection,
    pickModel: (m: string) => stageModel(m, models, local),
    pickTier: (tier: Tier, m: string) => setDraftTiers((cur) => ({ ...cur, [tier]: m })),
  };
}

export type ConnectionDraft = ReturnType<typeof useAgentConnectionDraft>;
