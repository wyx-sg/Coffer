// frontend/src/components/agents/AgentOverviewTab.tsx — the agent detail page's
// Overview tab: a compact type + config-dir summary plus this agent's LLM
// connection + model picker. Each agent picks its own connection (per-wire
// single-active projection via `activate`) and the connection's model (PATCH the
// active connection → re-projects ANTHROPIC_MODEL / the agent's model). The
// agent's wire is fixed by its type (claude_code → anthropic, codex → openai);
// ollama connections are internal-only and never offered here.
import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import { useListProviderModels } from "@/lib/hooks/useModelIntrospection";
import {
  useActivateProvider,
  useProviders,
  useUpdateProvider,
} from "@/lib/hooks/useProviders";

const CUSTOM = "__custom__";

export function AgentOverviewTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const modelInputId = useId();
  const wire = WIRE_BY_AGENT[agent.type];

  const providers = useProviders();
  const activate = useActivateProvider();
  const update = useUpdateProvider();
  const list = useListProviderModels();

  const [fetched, setFetched] = useState<string[]>([]);
  const [customModel, setCustomModel] = useState(false);
  const [customText, setCustomText] = useState("");

  // Connections this agent can use: same wire format (ollama is internal-only).
  const compatible = useMemo(
    () => (providers.data ?? []).filter((p) => p.wire_format === wire),
    [providers.data, wire],
  );
  const active = useMemo(() => compatible.find((p) => p.is_active) ?? null, [compatible]);

  const models = useMemo(() => {
    const out: string[] = [];
    if (active?.model) out.push(active.model);
    if (active?.fast_model) out.push(active.fast_model);
    for (const m of fetched) if (!out.includes(m)) out.push(m);
    return out;
  }, [active, fetched]);

  const introspect = () => {
    if (!active) return;
    list.mutate(
      { provider: wire, base_url: active.base_url, credential_ref: active.credential_ref },
      { onSuccess: (r) => setFetched(r.models) },
    );
  };

  const onPickConnection = (name: string) => {
    setFetched([]);
    setCustomModel(false);
    activate.mutate(name);
  };

  const onPickModel = (model: string) => {
    if (model === CUSTOM) {
      setCustomText("");
      setCustomModel(true);
      return;
    }
    if (active && model && model !== active.model) {
      update.mutate({ name: active.name, patch: { model } });
    }
  };

  const commitCustomModel = () => {
    const next = customText.trim();
    setCustomModel(false);
    if (active && next && next !== active.model) {
      update.mutate({ name: active.name, patch: { model: next } });
    }
  };

  return (
    <Card>
      <CardContent className="space-y-6 py-6">
        <dl className="grid grid-cols-[10rem_1fr] gap-y-3 text-sm">
          <dt className="text-muted-foreground">{t("agents.type")}</dt>
          <dd>{agent.type}</dd>
          <dt className="text-muted-foreground">{t("agents.configDir")}</dt>
          <dd className="font-mono text-xs">{agent.config_dir}</dd>
        </dl>

        {/* This agent's LLM connection + model. No connection library here — that
            lives on Settings → LLM Connections; this only switches which one
            this agent uses and which model. */}
        <div className="space-y-3 border-t border-border pt-4">
          <h3 className="text-sm font-medium">{t("agents.connection.title")}</h3>

          {compatible.length === 0 ? (
            // The "manage" hint is rendered once, by the always-on footer below;
            // the empty state shows only the empty message (no duplicate).
            <p className="text-sm text-muted-foreground">{t("agents.connection.empty")}</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="agent-connection">{t("agents.connection.label")}</Label>
                <Select
                  value={active?.name ?? ""}
                  onValueChange={onPickConnection}
                  disabled={activate.isPending}
                >
                  <SelectTrigger id="agent-connection" className="text-sm">
                    <SelectValue placeholder={t("agents.connection.none")} />
                  </SelectTrigger>
                  <SelectContent>
                    {compatible.map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor={customModel ? modelInputId : "agent-model"}>
                  {t("agents.connection.model")}
                </Label>
                {customModel ? (
                  <Input
                    id={modelInputId}
                    autoFocus
                    value={customText}
                    placeholder={t("agents.connection.customPlaceholder")}
                    aria-label={t("agents.connection.customLabel")}
                    onChange={(e) => setCustomText(e.target.value)}
                    onBlur={commitCustomModel}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        (e.target as HTMLInputElement).blur();
                      }
                    }}
                    className="text-sm"
                  />
                ) : (
                  <Select
                    value={active?.model ?? ""}
                    onValueChange={onPickModel}
                    onOpenChange={(open) => open && introspect()}
                    disabled={!active || update.isPending}
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
                      <SelectItem value={CUSTOM}>{t("agents.connection.customModel")}</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>
          )}
          <p className="text-xs text-muted-foreground">{t("agents.connection.manage")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
