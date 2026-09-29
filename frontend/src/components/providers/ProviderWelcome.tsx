// src/components/providers/ProviderWelcome.tsx — first run: no provider yet.
//
// Three ways in — an Anthropic-compatible endpoint, an OpenAI-compatible one,
// or a local runtime on this Mac — each opening Add with that preset; what
// the registered agents run on right now (their own login); and, while no
// provider carries Coffer's engine, the line saying distil and curation are
// paused, linking Settings › General where it is chosen.
import { useTranslation } from "react-i18next";
import { ChevronRight } from "lucide-react";

import { AgentBadge } from "@/components/agent/AgentBadge";
import { Button } from "@/components/ui/button";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentOut } from "@/lib/api/agents";
import type { Provider } from "@/lib/api/providers";
import type { PresetId } from "@/lib/providers/presets";
import { useOpenSettings } from "@/lib/settingsModal";
import { ProviderMark } from "./ProviderMark";

interface Props {
  agents: AgentOut[];
  /** Whether any provider carries Coffer's engine. */
  engineSet: boolean;
  onAdd: (preset: PresetId) => void;
}

type MarkOf = Pick<Provider, "base_url" | "protocol" | "local_runtime">;

const OPTIONS: { preset: PresetId; key: string; mark: MarkOf }[] = [
  {
    preset: "anthropic",
    key: "anthropic",
    mark: { base_url: "https://api.anthropic.com", protocol: "anthropic", local_runtime: null },
  },
  {
    preset: "openai",
    key: "openai",
    mark: { base_url: "https://api.openai.com/v1", protocol: "openai", local_runtime: null },
  },
  {
    preset: "ollama",
    key: "local",
    mark: { base_url: "http://localhost:11434", protocol: "ollama", local_runtime: null },
  },
];

export function ProviderWelcome({ agents, engineSet, onAdd }: Props) {
  const { t } = useTranslation();
  const openSettings = useOpenSettings();
  return (
    <div className="flex max-w-3xl flex-col gap-6 rounded-xl border border-border bg-surface-raised px-7 py-6">
      <div className="flex flex-col gap-1.5">
        <h2 className="text-md font-bold text-text">{t("providers.welcome.title")}</h2>
        <p className="max-w-prose text-sm text-text-muted">{t("providers.welcome.body")}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {OPTIONS.map((o) => (
          <button
            key={o.key}
            type="button"
            onClick={() => onAdd(o.preset)}
            className="flex flex-col items-start gap-2 rounded-xl border border-border p-3.5 text-left outline-none hover:bg-surface-hover focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            <ProviderMark provider={o.mark} size="md" />
            <span className="text-sm font-label text-text">
              {t(`providers.welcome.${o.key}.title`)}
            </span>
            <span className="text-xs text-text-muted">{t(`providers.welcome.${o.key}.body`)}</span>
          </button>
        ))}
      </div>
      {agents.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <h3 className="text-sm font-semibold text-text">{t("providers.welcome.rightNow")}</h3>
          <div className="flex flex-col">
            {agents.map((a) => (
              <div
                key={a.uid}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-border-subtle py-2"
              >
                <span className="inline-flex min-w-0 items-center gap-2.5">
                  <AgentBadge type={a.type} size="md" tooltip={false} />
                  <span className="text-sm font-label">{agentTypeLabel(a.type)}</span>
                  <span className="truncate font-mono text-xs text-text-muted">
                    {abbreviateHomePath(a.config_dir)}
                  </span>
                </span>
                <span className="text-xs text-text-muted">
                  {t(`providers.welcome.ownLogin.${a.type === "codex" ? "codex" : "claude_code"}`)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {engineSet ? null : (
        <p className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
          {t("providers.welcome.engineUnset")}
          <Button
            variant="link"
            size="sm"
            className="h-auto px-0"
            onClick={() => openSettings("general")}
          >
            {t("providers.welcome.engineLink")} <ChevronRight aria-hidden />
          </Button>
        </p>
      )}
    </div>
  );
}
