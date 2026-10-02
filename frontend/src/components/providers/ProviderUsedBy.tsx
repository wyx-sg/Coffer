// src/components/providers/ProviderUsedBy.tsx — the read-only Used by list of a provider's Overview.
//
// Each agent switched to the provider, with the model it runs, opens that
// agent's Model tab; Coffer's engine and speech to text, when the provider is
// flagged for them, open Settings › General. There is no switch, activate or
// revert control here: an agent's provider is changed only on its Model tab
// (spec provider-switching "Offer every connection operation on REST, CLI and
// web").
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ChevronRight, Cpu, Mic, type LucideIcon } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { TruncatedText } from "@/components/ui/truncated-text";
import { StatusDot } from "@/components/status/StatusDot";
import { agentTypeLabel } from "@/lib/agents/display";
import { agentTabPath } from "@/lib/agents/routes";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { useOpenSettings } from "@/lib/settingsModal";
import { Section } from "@/components/Section";

const ROW =
  "-mx-2 grid min-h-row grid-cols-[minmax(0,1fr)_150px_200px_16px] items-center gap-3 px-2 py-2 text-left text-text no-underline outline-none transition-colors duration-fast hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-ring";

function RowBody({
  lead,
  name,
  model,
  where,
  failing,
}: {
  lead: ReactNode;
  name: string;
  model: string | null;
  where: string;
  failing: boolean;
}) {
  const { t } = useTranslation();
  return (
    <>
      <span className="inline-flex min-w-0 items-center gap-2.5">
        {lead}
        <TruncatedText text={name} className="text-sm font-label" />
      </span>
      <TruncatedText text={model ?? t("common.emptyValue")} mono className="text-xs" />
      <span className="flex flex-col gap-0.5">
        <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
          <StatusDot tone={failing ? "err" : "ok"} size={7} />
          {failing ? t("providers.usedBy.failing") : t("providers.usedBy.runs")}
        </span>
        <span className="text-2xs text-text-subtle">{where}</span>
      </span>
      <ChevronRight className="size-4 text-text-subtle" aria-hidden />
    </>
  );
}

function IconTile({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-item bg-chip text-text-muted">
      <Icon className="size-3.5" aria-hidden />
    </span>
  );
}

export function ProviderUsedBy({ use, failing }: { use: ProviderUse; failing: boolean }) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  const settingsWhere = t("providers.usedBy.changeInSettings");
  const coffer = [
    use.engine && {
      key: "engine",
      icon: Cpu,
      name: t("providers.usedBy.engine"),
      model: use.engine.model,
    },
    use.transcribe && {
      key: "transcribe",
      icon: Mic,
      name: t("providers.usedBy.transcribe"),
      model: use.transcribe.model,
    },
  ].filter((r): r is { key: string; icon: LucideIcon; name: string; model: string | null } => !!r);
  const empty = use.agents.length === 0 && coffer.length === 0;

  return (
    <Section title={t("providers.usedBy.title")} help={t("providers.usedBy.readOnly")}>
      {empty ? (
        <p className="py-3 text-sm text-text-muted">{t("providers.usedBy.none")}</p>
      ) : (
        <div className="flex flex-col divide-y divide-border-subtle">
          {use.agents.map(({ agent, model }) => {
            const label = agentTypeLabel(agent.type);
            return (
              <Link key={agent.uid} to={agentTabPath(agent.type, "model")} className={ROW}>
                <RowBody
                  lead={<AgentBadge type={agent.type} size="md" tooltip={false} />}
                  name={label}
                  model={model}
                  where={t("providers.usedBy.changeInAgent", { agent: label })}
                  failing={failing}
                />
              </Link>
            );
          })}
          {coffer.map((c) => (
            <button
              key={c.key}
              type="button"
              className={ROW}
              onClick={() => openSettings("general")}
            >
              <RowBody
                lead={<IconTile icon={c.icon} />}
                name={c.name}
                model={c.model}
                where={settingsWhere}
                failing={failing}
              />
            </button>
          ))}
        </div>
      )}
    </Section>
  );
}
