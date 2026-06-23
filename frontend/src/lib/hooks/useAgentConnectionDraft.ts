// frontend/src/lib/hooks/useAgentConnectionDraft.ts — the draft → test → confirm
// state machine behind the Agent Overview LLM-connection panel.
//
// Picking a connection/model is a DRAFT: it stages a choice but projects nothing
// (spec 011 amendment 2026-06-23c). The user must «测试连接» (test-connection) a
// custom connection and only then «确认切换», which PATCHes the per-agent model
// binding and activates the connection — the only step that writes native config.
// Switching to the built-in login needs no test. The model lives on the agent
// binding, not the connection (spec 011 E3).
import { useEffect, useMemo, useState } from "react";

import type { AgentOut, AgentPatch } from "@/lib/api/agents";
import { WIRE_BY_AGENT } from "@/lib/api/providers";
import { usePatchAgent } from "@/lib/hooks/useAgents";
import { useListProviderModels, useTestConnection } from "@/lib/hooks/useModelIntrospection";
import { useActivateProvider, useProviders, useUseBuiltinProvider } from "@/lib/hooks/useProviders";

// Radix forbids an empty value, so the "use built-in login" option is a token.
export const BUILTIN = "__builtin__";

export function useAgentConnectionDraft(agent: AgentOut) {
  const wire = WIRE_BY_AGENT[agent.type];

  const providers = useProviders();
  const activate = useActivateProvider();
  const useBuiltin = useUseBuiltinProvider();
  const patchAgent = usePatchAgent();
  const list = useListProviderModels();
  const test = useTestConnection();

  // Filter by the connection's explicit compatible-agents set (not its wire), so
  // a connection the user routed to this agent type shows up even if its endpoint
  // speaks a different wire (the agnes case: an openai gateway → Claude Code).
  const compatible = useMemo(
    () => (providers.data ?? []).filter((p) => (p.compatible_agents ?? []).includes(agent.type)),
    [providers.data, agent.type],
  );
  const active = useMemo(() => compatible.find((p) => p.is_active) ?? null, [compatible]);

  // The APPLIED (currently projected) state: the active connection and the model(s)
  // bound to it. Built-in login = no active connection, no model override.
  const appliedConn = active?.name ?? BUILTIN;
  const appliedModel = active === null ? "" : (agent.model ?? "");
  const appliedFast = active === null ? "" : (agent.fast_model ?? "");

  // DRAFT state — re-syncs to the applied state whenever the latter changes
  // (initial load, after a confirm, an external change); a same-value refetch
  // leaves an in-progress draft untouched (the effect only fires when the applied
  // identity actually changes).
  const [draftConn, setDraftConn] = useState(appliedConn);
  const [draftModel, setDraftModel] = useState(appliedModel);
  const [draftFast, setDraftFast] = useState(appliedFast);
  const [fetched, setFetched] = useState<string[]>([]);

  useEffect(() => {
    setDraftConn(appliedConn);
    setDraftModel(appliedModel);
    setDraftFast(appliedFast);
    setFetched([]);
    test.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appliedConn, appliedModel, appliedFast]);

  const draftConnObj = useMemo(
    () => compatible.find((p) => p.name === draftConn) ?? null,
    [compatible, draftConn],
  );

  const models = useMemo(() => {
    const out: string[] = [];
    // Seed the staged model(s) so they show before the dropdown is opened
    // (introspect populates the rest on open).
    for (const m of [draftModel, draftFast]) if (m && !out.includes(m)) out.push(m);
    for (const m of fetched) if (!out.includes(m)) out.push(m);
    return out;
  }, [draftModel, draftFast, fetched]);

  // Introspect the DRAFT connection's endpoint using its OWN wire (how to call it),
  // which can differ from the agent's (an openai gateway routed to Claude Code).
  const introspect = () => {
    if (!draftConnObj) return;
    list.mutate(
      {
        provider: draftConnObj.protocol,
        base_url: draftConnObj.base_url,
        credential_ref: draftConnObj.credential_ref,
      },
      { onSuccess: (r) => setFetched(r.models) },
    );
  };

  const pickConnection = (name: string) => {
    setDraftConn(name);
    setDraftModel("");
    setDraftFast("");
    setFetched([]);
    test.reset();
    if (name === BUILTIN) return;
    const conn = compatible.find((p) => p.name === name);
    if (!conn) return;
    // Stage (do NOT apply) a default model so the user has something to test:
    // default both slots to the endpoint's first model.
    list.mutate(
      { provider: conn.protocol, base_url: conn.base_url, credential_ref: conn.credential_ref },
      {
        onSuccess: (r) => {
          setFetched(r.models);
          const def = r.models[0] ?? "";
          setDraftModel(def);
          if (wire === "anthropic") setDraftFast(def);
        },
      },
    );
  };

  // Changing a model invalidates any prior test result for the draft.
  const pickModel = (m: string) => {
    setDraftModel(m);
    test.reset();
  };
  const pickFast = (m: string) => {
    setDraftFast(m);
    test.reset();
  };

  const runTest = () => {
    if (!draftConnObj || !draftModel) return;
    test.mutate({
      provider: draftConnObj.protocol,
      model: draftModel,
      base_url: draftConnObj.base_url,
      credential_ref: draftConnObj.credential_ref,
    });
  };

  // Confirm = persist the per-agent binding, then activate so projection reads it.
  // Built-in confirm reverts the agent to its own login (no model override).
  const confirm = () => {
    if (draftConn === BUILTIN) {
      useBuiltin.mutate(wire);
      return;
    }
    const body: AgentPatch = { model: draftModel };
    if (wire === "anthropic" && draftFast) body.fast_model = draftFast;
    patchAgent.mutate({ name: agent.name, body }, { onSuccess: () => activate.mutate(draftConn) });
  };

  const draftIsBuiltin = draftConn === BUILTIN;
  const dirty =
    draftConn !== appliedConn || draftModel !== appliedModel || draftFast !== appliedFast;
  // A custom connection must pass a test (for the CURRENT draft — any model change
  // resets test.data) before it can be confirmed; built-in needs no test.
  const canConfirm = dirty && (draftIsBuiltin ? true : !!draftModel && test.data?.ok === true);
  const busy = activate.isPending || patchAgent.isPending || useBuiltin.isPending;

  return {
    wire,
    compatible,
    draftConn,
    draftModel,
    draftFast,
    models,
    draftIsBuiltin,
    dirty,
    canConfirm,
    busy,
    modelsDisabled: draftIsBuiltin || busy,
    testPending: test.isPending,
    testResult: test.data ?? null,
    introspect,
    pickConnection,
    pickModel,
    pickFast,
    runTest,
    confirm,
  };
}
