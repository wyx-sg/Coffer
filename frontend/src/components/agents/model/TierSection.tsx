// src/components/agents/model/TierSection.tsx — Claude Code's Model per tier: one model per tier, prefilled by Coffer, with Reset to suggested.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ConnectionDraft } from "@/lib/hooks/useAgentConnectionDraft";

interface Props {
  draft: ConnectionDraft;
}

export function TierSection({ draft: c }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  // A pinned tier stays selectable even when the list no longer offers it.
  const options = [...new Set([...c.models, ...Object.values(c.draftTiers)])].filter(Boolean);
  const summary = c.tiersAreSuggested
    ? t("agents.modelTab.tiers.suggested")
    : c.tiers
        .map((tier) => `${t(`agents.modelTab.tiers.names.${tier}`)}→${c.draftTiers[tier] ?? "—"}`)
        .join(" · ");
  const panel = "agent-tiers-panel";
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <div className="flex min-h-control-sm items-center gap-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panel}
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 items-center gap-1.5 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          <ChevronRight
            aria-hidden
            className={cn(
              "size-3.5 shrink-0 text-text-subtle transition-transform",
              open && "rotate-90",
            )}
          />
          <span className="text-sm font-semibold text-text">
            {t("agents.modelTab.tiers.title")}
          </span>
        </button>
        <HelpTip label={t("agents.modelTab.tiers.helpLabel")}>
          <p className="text-xs">{t("agents.modelTab.tiers.help")}</p>
        </HelpTip>
        {open ? (
          <button
            type="button"
            onClick={c.resetTiers}
            disabled={c.busy}
            className="ml-auto text-xs font-label text-accent-text hover:underline disabled:opacity-60"
          >
            {t("agents.modelTab.tiers.reset")}
          </button>
        ) : null}
      </div>
      {open ? (
        <div id={panel} className="flex flex-col gap-2">
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
                  onOpenChange={(o) => o && c.introspect()}
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
          <span className="text-xs text-text-subtle">{t("agents.modelTab.tiers.hint")}</span>
        </div>
      ) : (
        <p className="truncate pl-5 text-xs text-text-subtle" title={summary}>
          {summary}
        </p>
      )}
    </section>
  );
}
