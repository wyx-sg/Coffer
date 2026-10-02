// src/components/agents/model/ProviderChoices.tsx — the Model tab's Provider section: two radio cards (built-in login / custom provider); the custom one opens a searchable list of every compatible connection.
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";

import { Label } from "@/components/ui/label";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
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

const CUSTOM = "__custom__";

interface Choice {
  value: string;
  disabled?: boolean;
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
      p.secret_ref ? t("agents.modelTab.provider.keyInVault") : null,
      count > 0 ? t("agents.modelTab.provider.modelCount", { count }) : null,
    ]
      .filter(Boolean)
      .join(" · ");
  };
  const customOn = value !== BUILTIN;
  const choices: Choice[] = [
    {
      value: BUILTIN,
      title: t("agents.modelTab.provider.builtin"),
      detail: t(`agents.modelTab.provider.builtinDetail.${agentType}`),
    },
    {
      value: CUSTOM,
      title: t("agents.modelTab.provider.custom"),
      detail:
        connections.length === 0
          ? t("agents.modelTab.provider.customNone")
          : t("agents.modelTab.provider.customDetail"),
      disabled: connections.length === 0,
    },
  ];
  const options = connections.map((p) => ({
    value: p.uid,
    label: displayName(p),
    hint: detailOf(p),
  }));
  // Choosing "custom" stages the provider the agent already runs on, else the first.
  const choose = (choice: string) => {
    if (choice === BUILTIN) return onChange(BUILTIN);
    if (customOn) return;
    const target = connections.find((p) => p.uid === applied) ?? connections[0];
    if (target) onChange(target.uid);
  };

  // Arrow keys move the choice, as in any radio group.
  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key] ?? 0;
    if (step === 0 || disabled) return;
    event.preventDefault();
    const next = (index + step + choices.length) % choices.length;
    if (choices[next].disabled) return;
    choose(choices[next].value);
    refs.current[next]?.focus();
  };

  return (
    <Section
      title={t("agents.modelTab.provider.title")}
      className="min-w-0"
      help={
        <p className="text-xs">
          {t(`agents.modelTab.provider.helpByType.${agentType}`, { agent })}
        </p>
      }
    >
      <div
        role="radiogroup"
        aria-label={t("agents.modelTab.provider.title")}
        className="flex min-w-0 flex-col gap-2"
      >
        {choices.map((choice, index) => {
          const checked = choice.value === CUSTOM ? customOn : value === BUILTIN;
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
              disabled={disabled || choice.disabled}
              onClick={() => choose(choice.value)}
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
              {(choice.value === CUSTOM ? applied !== BUILTIN : applied === BUILTIN) ? (
                <span className="inline-flex h-5 shrink-0 items-center rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
                  {t("agents.modelTab.provider.current")}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      {customOn && connections.length > 0 ? (
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="agent-provider">{t("agents.modelTab.provider.custom")}</Label>
          <Combobox
            id="agent-provider"
            value={value}
            options={options}
            onChange={onChange}
            placeholder={t("agents.modelTab.provider.customPick")}
            emptyMessage={t("agents.modelTab.provider.customSearchEmpty")}
            disabled={disabled}
          />
        </div>
      ) : null}
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
    </Section>
  );
}
