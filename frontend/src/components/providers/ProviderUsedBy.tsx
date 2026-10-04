// src/components/providers/ProviderUsedBy.tsx — the read-only Used by list of a provider.
//
// One bordered list of like rows: each agent switched to the provider, then
// speech to text when the provider is flagged for it.
// Every row says where it is changed, as a link — "Codex › Change model" opens
// that agent's page with its Change model dialog; "Settings › General" opens
// Settings. Healthy rows carry no status word and no chevron; a provider's
// fault shows in its header and its own section, never row by row.
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Mic, type LucideIcon } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Section } from "@/components/Section";
import { TruncatedText } from "@/components/ui/truncated-text";
import { agentTypeLabel } from "@/lib/agents/display";
import { agentBasePath } from "@/lib/agents/routes";
import type { ProviderUse } from "@/lib/providers/usedBy";
import { useOpenSettings } from "@/lib/settingsModal";

const LINK =
  "text-xs font-label text-accent-text no-underline outline-none hover:underline focus-visible:ring-2 focus-visible:ring-focus-ring";

function Row({
  lead,
  name,
  where,
  model,
}: {
  lead: ReactNode;
  name: string;
  where: ReactNode;
  model: string | null;
}) {
  const { t } = useTranslation();
  return (
    <li className="grid min-h-row grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-3.5 py-2">
      <span className="inline-flex min-w-0 items-center gap-2.5">
        {lead}
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-label text-text">{name}</span>
          <span className="text-xs text-text-muted">{where}</span>
        </span>
      </span>
      <TruncatedText
        text={model ?? t("common.emptyValue")}
        mono
        className="max-w-[240px] text-xs text-text"
      />
    </li>
  );
}

function IconTile({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-md bg-chip text-text-muted">
      <Icon className="size-3.5" aria-hidden />
    </span>
  );
}

export function ProviderUsedBy({ use }: { use: ProviderUse }) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  const settings = (
    <>
      {t("providers.usedBy.changeIt")}{" "}
      <button type="button" className={LINK} onClick={() => openSettings("general")}>
        {t("providers.usedBy.settingsGeneral")}
      </button>
    </>
  );
  const coffer = [
    use.transcribe && {
      key: "transcribe",
      icon: Mic,
      name: t("providers.usedBy.transcribe"),
      model: use.transcribe.model,
    },
  ].filter((r): r is { key: string; icon: LucideIcon; name: string; model: string | null } => !!r);
  const empty = use.agents.length === 0 && coffer.length === 0;

  return (
    <Section title={t("providers.usedBy.title")} gap="tight">
      <p className="text-xs text-text-muted">{t("providers.usedBy.lead")}</p>
      {empty ? (
        <p className="py-2 text-sm text-text-muted">{t("providers.usedBy.none")}</p>
      ) : (
        <ul className="mt-1 divide-y divide-border-subtle overflow-hidden rounded-lg border border-border-subtle bg-surface-raised">
          {use.agents.map(({ agent, model }) => {
            const label = agentTypeLabel(agent.type);
            return (
              <Row
                key={agent.uid}
                lead={<AgentBadge type={agent.type} size="md" tooltip={false} />}
                name={label}
                model={model}
                where={
                  <>
                    {t("providers.usedBy.changeIt")}{" "}
                    <Link to={`${agentBasePath(agent.type)}?change-model=1`} className={LINK}>
                      {t("providers.usedBy.changeModel", { agent: label })}
                    </Link>
                  </>
                }
              />
            );
          })}
          {coffer.map((c) => (
            <Row
              key={c.key}
              lead={<IconTile icon={c.icon} />}
              name={c.name}
              model={c.model}
              where={settings}
            />
          ))}
        </ul>
      )}
    </Section>
  );
}
