// frontend/src/kinds/channel/ChannelModelFields.tsx — the channel's own model
// curation (spec channels FR-071), shared by the add and edit dialogs.
//
// WHY IT LIVES ON THE CHANNEL. The catalogue an agent reports is cumulative and
// account-blind: it names every model the installed CLI has heard of, including
// ones this account is not entitled to run, and no local fact separates them.
// Someone has to say — but the AGENT is the wrong place to say it, because an
// agent has no audience: curating it would narrow a phone chat and the agent
// page at once. A channel does have one. So the two answers are the channel's:
//
// * «默认模型» — the model a NEW conversation on this channel opens on. An
//   explicit "not pinned" choice is always offered; unpinned means the agent's
//   own default applies, which is how every channel nobody configured behaves.
// * «可选范围» — the models this channel may use at all. The `/model` card
//   offers exactly these and `/model <id>` outside them is refused. Ticking
//   NOTHING means NO RESTRICTION — every model the bound agent offers — never
//   "no models".
//
// Two rules the form enforces so a submit cannot fail on something visible
// here. The default must be inside a non-empty range (the backend rejects it
// too, and a channel that opened conversations on a model it then refuses would
// be broken by construction) — un-ticking the pinned model therefore unpins it.
// And the ids belong to ONE agent: changing the bound agent drops both, rather
// than submitting a Claude id to a Codex channel.
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useAgentModels } from "@/lib/hooks/useAgentModels";
import { defaultModelOutOfRange } from "./modelCuration";

/** Radix reserves the empty string, so "not pinned" needs a sentinel value. */
export const UNPINNED = "__unpinned__";

interface Props {
  /** The chat provider key of the channel's bound agent (`default_agent`). */
  agentKey: string;
  /** The pinned model id, or `""` for "not pinned". */
  defaultModel: string;
  /** The allowed range; `[]` = unrestricted. */
  models: string[];
  onDefaultModelChange: (model: string) => void;
  onModelsChange: (models: string[]) => void;
  /** Prefix for the rendered element ids, so two dialogs never collide. */
  idPrefix: string;
}

export function ChannelModelFields({
  agentKey,
  defaultModel,
  models,
  onDefaultModelChange,
  onModelsChange,
  idPrefix,
}: Props) {
  const { t } = useTranslation();
  const catalogue = useAgentModels(agentKey);
  const offered = catalogue.data ?? [];

  // The ids name models of ONE agent. When the binding changes they stop
  // meaning anything, so they go — re-validating against a catalogue that is
  // still loading for the new key would only guess. A ref rather than state:
  // this must fire on a CHANGE, never on the first render of a stored config.
  const lastAgent = useRef(agentKey);
  useEffect(() => {
    if (lastAgent.current === agentKey) return;
    lastAgent.current = agentKey;
    onDefaultModelChange("");
    onModelsChange([]);
  }, [agentKey, onDefaultModelChange, onModelsChange]);

  // The default is picked out of the range once there is one; otherwise out of
  // the whole catalogue. A pinned id neither list carries (a model the last CLI
  // upgrade dropped) stays selectable rather than silently vanishing.
  const rangeOrCatalogue = models.length > 0 ? models : offered.map((m) => m.id);
  const options = rangeOrCatalogue.includes(defaultModel)
    ? rangeOrCatalogue
    : defaultModel
      ? [defaultModel, ...rangeOrCatalogue]
      : rangeOrCatalogue;

  const toggle = (id: string) => {
    if (models.includes(id)) {
      const next = models.filter((m) => m !== id);
      // Narrowing the range past the pinned model unpins it: the backend
      // refuses that pair, and silently submitting it would fail the save.
      if (next.length > 0 && defaultModel === id) onDefaultModelChange("");
      onModelsChange(next);
    } else {
      onModelsChange([...models, id]);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor={`${idPrefix}-default-model`}>{t("channels.models.defaultLabel")}</Label>
        <Select
          value={defaultModel || UNPINNED}
          onValueChange={(v) => onDefaultModelChange(v === UNPINNED ? "" : v)}
        >
          <SelectTrigger
            id={`${idPrefix}-default-model`}
            aria-label={t("channels.models.defaultLabel")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={UNPINNED}>{t("channels.models.defaultNone")}</SelectItem>
            {options.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">{t("channels.models.defaultHint")}</p>
        {defaultModelOutOfRange(defaultModel, models) && (
          <p className="text-xs text-destructive" role="alert">
            {t("channels.models.outOfRange")}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label>{t("channels.models.rangeLabel")}</Label>
        <p className="text-xs text-muted-foreground">{t("channels.models.rangeHint")}</p>
        {catalogue.isError ? (
          <p className="text-xs text-destructive" role="alert">
            {t("channels.models.loadFailed")} {translateApiError(t, catalogue.error)}
          </p>
        ) : catalogue.isLoading ? (
          <p className="text-xs text-muted-foreground">{t("common.loading")}</p>
        ) : offered.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("channels.models.empty")}</p>
        ) : (
          <>
            <ul className="max-h-52 space-y-1 overflow-y-auto">
              {offered.map((m) => (
                <li key={m.id}>
                  <label className="flex cursor-pointer items-baseline gap-2 text-sm">
                    <Checkbox
                      checked={models.includes(m.id)}
                      onChange={() => toggle(m.id)}
                      aria-label={m.id}
                    />
                    <span className="font-mono text-xs">{m.id}</span>
                    {m.label && m.label !== m.id && (
                      <span className="text-muted-foreground">{m.label}</span>
                    )}
                  </label>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              {models.length === 0
                ? t("channels.models.unrestricted")
                : t("channels.models.chosenCount", {
                    chosen: models.length,
                    total: offered.length,
                  })}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
