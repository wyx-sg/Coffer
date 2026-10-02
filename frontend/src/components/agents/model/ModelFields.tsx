// src/components/agents/model/ModelFields.tsx — the Model tab's Model section: the model picker (read-only on the built-in login) and Effort.
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AgentType } from "@/lib/api/agents";
import { agentTypeLabel } from "@/lib/agents/display";
import type { ConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";
import { EffortControl } from "./EffortControl";

interface Props {
  agentType: AgentType;
  draft: ConnectionDraft;
}

export function ModelFields({ agentType, draft: c }: Props) {
  const { t } = useTranslation();
  const agent = agentTypeLabel(agentType);

  return (
    <Section title={t("agents.modelTab.model.title")} className="min-w-0">
      <div className="flex flex-col gap-3.5">
        {c.draftIsBuiltin ? (
          // Nothing reads the agent's model binding on its own login (chat turns
          // run on Claude Code's / Codex's own model, and switching back to the
          // built-in login strips the keys Coffer wrote), so the default is
          // shown greyed out, with the reason: /model in a session switches it.
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className="text-xs font-label text-text-muted">
              {t("agents.modelTab.model.label")}
            </span>
            <div
              aria-disabled
              className="flex h-control-md cursor-not-allowed items-center rounded-md border border-border-subtle bg-surface-sunken px-2.5 font-mono text-xs text-text-subtle opacity-70"
            >
              {c.builtinDefault
                ? t("agents.modelTab.model.builtinDefault", { model: c.builtinDefault.id, agent })
                : "—"}
            </div>
            <span className="text-xs text-text-subtle">
              {t("agents.modelTab.model.builtinHint", { agent })}
            </span>
          </div>
        ) : (
          <div className="flex min-w-0 flex-col gap-1.5">
            <Label htmlFor="agent-model" required>
              {t("agents.modelTab.model.label")}
            </Label>
            <Select
              value={c.draftModel}
              onValueChange={c.pickModel}
              onOpenChange={(open) => open && c.introspect()}
              disabled={c.busy}
            >
              <SelectTrigger id="agent-model" className="font-mono text-xs">
                <SelectValue placeholder={t("agents.modelTab.model.placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {c.models.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-xs text-text-subtle">{t("agents.modelTab.model.hint")}</span>
          </div>
        )}

        {c.effortLevels.length > 0 ? (
          <EffortControl
            levels={c.effortLevels}
            value={c.draftIsBuiltin ? null : c.draftEffort}
            onChange={c.pickEffort}
            readOnly={c.draftIsBuiltin || c.busy}
            disabledLook={c.draftIsBuiltin}
            hint={t(
              c.draftIsBuiltin
                ? "agents.modelTab.effort.builtinHint"
                : "agents.modelTab.effort.hint",
              { agent },
            )}
          />
        ) : c.draftIsBuiltin ? null : (
          <p className="text-xs text-text-subtle">
            {t(c.draftModel ? "agents.modelTab.effort.hidden" : "agents.modelTab.effort.choose")}
          </p>
        )}
      </div>
    </Section>
  );
}
