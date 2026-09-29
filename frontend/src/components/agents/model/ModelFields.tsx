// src/components/agents/model/ModelFields.tsx — the Model tab's Model section: the model picker (read-only on the built-in login) and Effort.
import { useTranslation } from "react-i18next";

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
    <section className="flex min-w-0 flex-col gap-2.5">
      <h3 className="min-h-[26px] text-sm font-semibold leading-[26px] text-text">
        {t("agents.modelTab.model.title")}
      </h3>
      <div className="flex flex-col gap-3.5">
        {c.draftIsBuiltin ? (
          // Nothing reads the agent's model binding on its own login, so the
          // default is shown, not offered: /model in a session switches it.
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className="text-xs font-label text-text">{t("agents.modelTab.model.label")}</span>
            {c.builtinDefault ? (
              <div className="flex h-control-md items-center rounded-md border border-border-subtle bg-surface-sunken px-2.5 font-mono text-xs text-text">
                {t("agents.modelTab.model.builtinDefault", { model: c.builtinDefault.id, agent })}
              </div>
            ) : null}
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
            value={c.draftEffort}
            onChange={c.pickEffort}
            readOnly={c.draftIsBuiltin || c.busy}
            hint={t(
              c.draftIsBuiltin
                ? "agents.modelTab.effort.builtinHint"
                : "agents.modelTab.effort.hint",
              { agent },
            )}
          />
        ) : (
          <p className="text-xs text-text-subtle">{t("agents.modelTab.effort.hidden")}</p>
        )}
      </div>
    </section>
  );
}
