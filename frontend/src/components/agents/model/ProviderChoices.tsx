// src/components/agents/model/ProviderChoices.tsx — the Model tab's Provider section: built-in login plus every compatible connection, as radio cards.
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { HelpTip } from "@/components/HelpTip";
import { Button } from "@/components/ui/button";
import type { AgentType } from "@/lib/api/agents";
import { modelIds, type Provider } from "@/lib/api/providers";
import { agentTypeLabel } from "@/lib/agents/display";
import { BUILTIN } from "@/lib/hooks/useAgentConnectionDraft";
import { displayName } from "@/lib/resourceTitle";
import { cn } from "@/lib/utils";

const PROVIDERS_PAGE = "/model-providers";

function hostOf(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

interface Choice {
  value: string;
  title: string;
  detail: string;
}

interface Props {
  agentType: AgentType;
  connections: Provider[];
  /** The draft choice (a connection uid or BUILTIN). */
  value: string;
  /** The applied choice, marked "Current". */
  applied: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function ProviderChoices({
  agentType,
  connections,
  value,
  applied,
  disabled,
  onChange,
}: Props) {
  const { t } = useTranslation();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const agent = agentTypeLabel(agentType);

  const detailOf = (p: Provider) => {
    const count = modelIds(p.models ?? [], "text").length;
    return [
      hostOf(p.base_url),
      p.credential_ref ? t("agents.modelTab.provider.keyInVault") : null,
      count > 0 ? t("agents.modelTab.provider.modelCount", { count }) : null,
    ]
      .filter(Boolean)
      .join(" · ");
  };
  const choices: Choice[] = [
    {
      value: BUILTIN,
      title: t("agents.modelTab.provider.builtin"),
      detail: t(`agents.modelTab.provider.builtinDetail.${agentType}`),
    },
    ...connections.map((p) => ({ value: p.uid, title: displayName(p), detail: detailOf(p) })),
  ];

  // Arrow keys move the choice, as in any radio group.
  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key] ?? 0;
    if (step === 0 || disabled) return;
    event.preventDefault();
    const next = (index + step + choices.length) % choices.length;
    onChange(choices[next].value);
    refs.current[next]?.focus();
  };

  return (
    <section className="flex min-w-0 flex-col gap-2.5">
      <div className="flex min-h-[26px] items-center gap-2">
        <h3 className="text-sm font-semibold text-text">{t("agents.modelTab.provider.title")}</h3>
        <HelpTip label={t("agents.modelTab.provider.helpLabel")}>
          <p className="text-xs">{t("agents.modelTab.provider.help", { agent })}</p>
        </HelpTip>
      </div>
      <div
        role="radiogroup"
        aria-label={t("agents.modelTab.provider.title")}
        className="flex min-w-0 flex-col gap-2"
      >
        {choices.map((choice, index) => {
          const checked = choice.value === value;
          return (
            <button
              key={choice.value}
              ref={(el) => {
                refs.current[index] = el;
              }}
              type="button"
              role="radio"
              aria-checked={checked}
              tabIndex={checked ? 0 : -1}
              disabled={disabled}
              onClick={() => onChange(choice.value)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={cn(
                "flex items-center gap-3 rounded-lg border px-3.5 py-2.5 text-left outline-none transition-colors duration-fast focus-visible:ring-2 focus-visible:ring-focus-ring disabled:opacity-60",
                checked
                  ? "border-accent bg-accent-soft"
                  : "border-border bg-surface-raised hover:bg-surface-hover",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "inline-flex size-4 shrink-0 items-center justify-center rounded-full border",
                  checked ? "border-transparent bg-accent" : "border-border bg-surface-raised",
                )}
              >
                {checked ? <span className="size-1.5 rounded-full bg-on-accent" /> : null}
              </span>
              <span className="flex min-w-0 flex-grow flex-col gap-0.5">
                <span className="text-sm font-semibold text-text">{choice.title}</span>
                <span className="break-all text-xs text-text-muted">{choice.detail}</span>
              </span>
              {choice.value === applied ? (
                <span className="inline-flex h-5 shrink-0 items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
                  {t("agents.modelTab.provider.current")}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      {connections.length === 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-border px-3.5 py-2.5">
          <div className="flex min-w-0 flex-grow flex-col gap-0.5">
            <span className="text-sm font-semibold text-text">
              {t("agents.modelTab.provider.noneTitle")}
            </span>
            <span className="text-xs text-text-muted">
              {t(`agents.modelTab.provider.noneBody.${agentType}`)}
            </span>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link to={PROVIDERS_PAGE}>
              <Plus aria-hidden />
              {t("agents.modelTab.provider.addConnection")}
            </Link>
          </Button>
        </div>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-text-subtle">{t("agents.modelTab.provider.livesOn")}</span>
        <Link to={PROVIDERS_PAGE} className="font-label text-accent-text hover:underline">
          {t("agents.modelTab.provider.manage")}
        </Link>
      </div>
    </section>
  );
}
