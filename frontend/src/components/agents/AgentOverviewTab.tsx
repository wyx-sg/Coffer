// frontend/src/components/agents/AgentOverviewTab.tsx — the agent detail page's
// Overview tab: type + config-dir summary plus this agent's LLM connection and
// its per-agent model binding. The agent picks its connection (per-wire
// single-active projection via `activate`) and its OWN model(s) — the model
// lives on the agent binding now, not the connection (spec 011 amendment
// 2026-06-22b). Claude Code exposes two slots (primary + fast); Codex one.
// Picking a model PATCHes the agent binding, then re-activates the connection to
// re-project. The agent's wire is fixed by its type; ollama is internal-only.
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentOut } from "@/lib/api/agents";
import { WIRE_BY_AGENT } from "@/lib/api/providers";
import { usePatchAgent } from "@/lib/hooks/useAgents";
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import { useActivateProvider, useProviders, useUseBuiltinProvider } from "@/lib/hooks/useProviders";

// Radix forbids an empty value, so the "use built-in login" option is a token.
const BUILTIN = "__builtin__";

export function AgentOverviewTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const wire = WIRE_BY_AGENT[agent.type];

  const providers = useProviders();
  const activate = useActivateProvider();
  const useBuiltin = useUseBuiltinProvider();
  const patchAgent = usePatchAgent();
  const list = useListProviderModels();

  const [fetched, setFetched] = useState<string[]>([]);

  const compatible = useMemo(
    () => (providers.data ?? []).filter((p) => p.protocol === wire),
    [providers.data, wire],
  );
  const active = useMemo(() => compatible.find((p) => p.is_active) ?? null, [compatible]);

  const models = useMemo(() => {
    const out: string[] = [];
    // Seed the agent's bound model(s) so a correctly-bound agent shows them
    // before the dropdown is opened (introspect populates the rest on open).
    // The connection no longer carries a model (spec 011 E3).
    for (const m of [agent.model, agent.fast_model]) if (m && !out.includes(m)) out.push(m);
    for (const m of fetched) if (!out.includes(m)) out.push(m);
    return out;
  }, [agent.model, agent.fast_model, fetched]);

  const introspect = () => {
    if (!active) return;
    list.mutate(
      { provider: wire, base_url: active.base_url, credential_ref: active.credential_ref },
      { onSuccess: (r) => setFetched(r.models) },
    );
  };

  const onPickConnection = (name: string) => {
    setFetched([]);
    if (name === BUILTIN) {
      useBuiltin.mutate(wire);
      return;
    }
    activate.mutate(name);
  };

  // Bind a model on THIS agent, then re-activate so projection re-reads it.
  const reproject = () => active && activate.mutate(active.name);
  const bindPrimary = (model: string) =>
    patchAgent.mutate({ name: agent.name, body: { model } }, { onSuccess: reproject });
  const bindFast = (fast: string) =>
    patchAgent.mutate({ name: agent.name, body: { fast_model: fast } }, { onSuccess: reproject });

  // The model lives on the per-agent binding (spec 011 E3) — not the connection.
  // When the agent is on the built-in login (no active Coffer connection) Coffer
  // does not override its model, so the model slots show empty + disabled.
  const usingBuiltin = active === null;
  const primaryModel = usingBuiltin ? "" : (agent.model ?? "");
  const fastModel = usingBuiltin ? "" : (agent.fast_model ?? "");
  const busy = activate.isPending || patchAgent.isPending;

  return (
    <Card>
      <CardContent className="space-y-6 py-6">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-3 text-sm">
          <dt className="text-muted-foreground">{t("agents.type")}</dt>
          <dd>{agent.type}</dd>
          <dt className="text-muted-foreground">{t("agents.configDir")}</dt>
          <dd className="font-mono text-xs">{agent.config_dir}</dd>
        </dl>

        <div className="space-y-3 border-t border-border pt-4">
          <h3 className="text-sm font-medium">{t("agents.connection.title")}</h3>

          {/* The connection dropdown always renders — even with no configured
              connections it defaults to the built-in login, never an empty
              "no connection" state. */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="agent-connection">{t("agents.connection.label")}</Label>
              <Select
                value={active?.name ?? BUILTIN}
                onValueChange={onPickConnection}
                disabled={activate.isPending || useBuiltin.isPending}
              >
                <SelectTrigger id="agent-connection" className="text-sm">
                  <SelectValue placeholder={t("agents.connection.none")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={BUILTIN}>{t("agents.connection.builtin")}</SelectItem>
                  {compatible.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="agent-model">{t("agents.connection.model")}</Label>
              <Select
                value={primaryModel}
                onValueChange={bindPrimary}
                onOpenChange={(open) => open && introspect()}
                disabled={usingBuiltin || busy}
              >
                <SelectTrigger id="agent-model" className="text-sm">
                  <SelectValue placeholder={t("agents.connection.none")} />
                </SelectTrigger>
                <SelectContent>
                  {models.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Claude Code's small/fast slot (ANTHROPIC_SMALL_FAST_MODEL); Codex
                has no second slot. */}
            {wire === "anthropic" && (
              <div className="space-y-1.5">
                <Label htmlFor="agent-fast-model">{t("agents.connection.fastModel")}</Label>
                <Select
                  value={fastModel}
                  onValueChange={bindFast}
                  onOpenChange={(open) => open && introspect()}
                  disabled={usingBuiltin || busy}
                >
                  <SelectTrigger id="agent-fast-model" className="text-sm">
                    <SelectValue placeholder={t("agents.connection.none")} />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          <p className="text-xs text-muted-foreground">{t("agents.connection.manage")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
