// src/components/agents/model/TierSection.tsx — Claude Code's Model per tier: one model per tier, prefilled by Coffer, with Reset to suggested.
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { Section } from "@/components/Section";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";

interface Props {
  draft: ConnectionDraft;
}

export function TierSection({ draft: c }: Props) {
  const { t } = useTranslation();
  // A pinned tier stays selectable even when the list no longer offers it.
  const options = [...new Set([...c.models, ...Object.values(c.draftTiers)])].filter(Boolean);
  return (
    <Section
      title={t("agents.modelTab.tiers.title")}
      className="min-w-0"
      aside={
        <>
          <HelpTip label={t("agents.modelTab.tiers.helpLabel")}>
            <p className="text-xs">{t("agents.modelTab.tiers.help")}</p>
          </HelpTip>
          <button
            type="button"
            onClick={c.resetTiers}
            disabled={c.busy}
            className="ml-auto text-xs font-label text-accent-text hover:underline disabled:opacity-60"
          >
            {t("agents.modelTab.tiers.reset")}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-2">
        {c.tiers.map((tier) => {
          const id = `agent-tier-${tier}`;
          const label = t(`agents.modelTab.tiers.names.${tier}`);
          return (
            <div key={tier} className="grid grid-cols-[90px_minmax(0,1fr)] items-center gap-3">
              <label htmlFor={id} className="text-xs font-label text-text">
                {label}
              </label>
              <Select
                value={c.draftTiers[tier] ?? ""}
                onValueChange={(m) => c.pickTier(tier, m)}
                onOpenChange={(open) => open && c.introspect()}
                disabled={c.busy}
              >
                <SelectTrigger id={id} className="font-mono text-xs">
                  <SelectValue placeholder={t("agents.modelTab.model.placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  {options.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          );
        })}
      </div>
      <span className="text-xs text-text-subtle">{t("agents.modelTab.tiers.hint")}</span>
    </Section>
  );
}
