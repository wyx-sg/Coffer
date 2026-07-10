// frontend/src/components/agents/AgentOverviewTab.tsx — the agent detail page's
// Overview tab: type + config-dir summary plus this agent's LLM connection and
// its per-agent model binding. Picking a connection/model is a DRAFT — the user
// stages a choice, must «测试连接», then «确认切换» to apply it (spec 011 amendment
// 2026-06-23c). The draft → test → confirm state machine lives in
// useAgentConnectionDraft; this file is presentation only. Claude Code exposes two
// model slots (primary + fast); Codex one.
import { useTranslation } from "react-i18next";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
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
import { facetSupported } from "@/lib/api/agentCapabilities";
import { BUILTIN, useAgentConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";

export function AgentOverviewTab({ agent }: { agent: AgentOut }) {
  const { t } = useTranslation();
  const c = useAgentConnectionDraft(agent);

  // FR-003a: a type without provider projection gets the uniform "not
  // supported" note instead of a functional-looking picker that can never
  // offer a compatible connection.
  if (!facetSupported(agent, "connections")) {
    return (
      <Card>
        <CardContent className="space-y-6 py-6">
          <dl className="grid grid-cols-[10rem_1fr] gap-y-3 text-sm">
            <dt className="text-muted-foreground">{t("agents.type")}</dt>
            <dd>{agent.type}</dd>
            <dt className="text-muted-foreground">{t("agents.configDir")}</dt>
            <dd className="font-mono text-xs">{agent.config_dir}</dd>
          </dl>
          <div className="space-y-1 border-t border-border pt-4">
            <h3 className="text-sm font-medium">{t("agents.connection.title")}</h3>
            <p className="text-sm text-muted-foreground">
              {t("agents.facetUnsupported.connections")}
            </p>
            {agent.type === "cursor" && (
              <p className="text-xs text-muted-foreground">
                {t("agents.facetUnsupported.cursorConnectionsReason")}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

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
              "no connection" state. Picking is a draft; nothing applies until
              «确认切换». */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="agent-connection">{t("agents.connection.label")}</Label>
              <Select value={c.draftConn} onValueChange={c.pickConnection} disabled={c.busy}>
                <SelectTrigger id="agent-connection" className="text-sm">
                  <SelectValue placeholder={t("agents.connection.none")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={BUILTIN}>{t("agents.connection.builtin")}</SelectItem>
                  {c.compatible.map((p) => (
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
                value={c.draftModel}
                onValueChange={c.pickModel}
                onOpenChange={(open) => open && c.introspect()}
                disabled={c.modelsDisabled}
              >
                <SelectTrigger id="agent-model" className="text-sm">
                  <SelectValue placeholder={t("agents.connection.none")} />
                </SelectTrigger>
                <SelectContent>
                  {c.models.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Claude Code's small/fast slot (ANTHROPIC_SMALL_FAST_MODEL); Codex
                has no second slot. */}
            {c.wire === "anthropic" && (
              <div className="space-y-1.5">
                <Label htmlFor="agent-fast-model">{t("agents.connection.fastModel")}</Label>
                <Select
                  value={c.draftFast}
                  onValueChange={c.pickFast}
                  onOpenChange={(open) => open && c.introspect()}
                  disabled={c.modelsDisabled}
                >
                  <SelectTrigger id="agent-fast-model" className="text-sm">
                    <SelectValue placeholder={t("agents.connection.none")} />
                  </SelectTrigger>
                  <SelectContent>
                    {c.models.map((m) => (
                      <SelectItem key={m} value={m}>
                        {m}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Test → confirm: a custom connection must be tested before it can be
              switched to; built-in confirms straight away. */}
          <div className="flex flex-wrap items-center gap-3">
            {!c.draftIsBuiltin && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={c.runTest}
                disabled={!c.draftModel || c.testPending}
              >
                {c.testPending && <Loader2 className="mr-1 size-3.5 animate-spin" />}
                {t("settings.models.testConnection")}
              </Button>
            )}
            <Button type="button" size="sm" onClick={c.confirm} disabled={!c.canConfirm || c.busy}>
              {c.busy ? t("common.saving") : t("agents.connection.confirm")}
            </Button>
            {c.testResult && (
              <span
                role="status"
                className={`flex items-center gap-1 text-xs ${
                  c.testResult.ok ? "text-green-600" : "text-destructive"
                }`}
              >
                {c.testResult.ok ? (
                  <CheckCircle2 className="size-3.5" />
                ) : (
                  <XCircle className="size-3.5" />
                )}
                {c.testResult.message}
              </span>
            )}
            {c.dirty && !c.draftIsBuiltin && !c.testResult?.ok && (
              <span className="text-xs text-muted-foreground">
                {t("agents.connection.testFirst")}
              </span>
            )}
          </div>

          <p className="text-xs text-muted-foreground">{t("agents.connection.manage")}</p>
        </div>
      </CardContent>
    </Card>
  );
}
