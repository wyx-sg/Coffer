// src/components/settings/cofferModel/ModelPairRow.tsx — one picker of the Speech-to-text section.
//
// A provider, then a model from that provider's list, a Test button, and the
// picker's state on one line under its description (spec internal-engine
// "Show the speech-to-text pair in Settings › General"):
//
//   • not set — either half missing; the caller says what Coffer does without it
//   • set     — both halves chosen, not tested in this visit
//   • answering / failing — the last Test in this visit, on this exact pair
//
// Each half saves on selection, like every settings surface (no Save button).
// Test only reads: a failure shows the endpoint's words here and changes
// nothing. The engine and speech rows differ only in which flag and which
// modality they read, so both are this one row.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { StatusWord } from "@/components/status/StatusWord";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Provider } from "@/lib/api/providers";
import { useModelPairTest, type PairTestMode } from "@/lib/hooks/useModelTest";
import { toneTextClass } from "@/lib/statusColors";

/** The "no model" option. Underscored so it cannot collide with a real model
 *  id, which is any opaque string the vendor chose. */
const OFF_VALUE = "__off__";

export interface ModelPairRowProps {
  title: string;
  description: string;
  providers: Provider[];
  selected: Provider | null;
  onProvider: (uid: string) => void;
  providerBusy: boolean;
  providerLabel: string;
  providerPlaceholder: string;
  /** The saved model id, "" for none. */
  model: string;
  options: string[];
  /** `null` clears the model (only offered when `offLabel` is given). */
  onModel: (model: string | null) => void;
  modelBusy: boolean;
  modelLabel: string;
  modelPlaceholder: string;
  /** Offer clearing the model as an option of its own. */
  offLabel?: string;
  /** What Coffer does while this picker is not set. */
  notSet: string;
  /** What waits while this picker fails, after the endpoint's error. */
  failingTail: string;
  /** How Test checks the pair: a chat request, or the endpoint's model list. */
  testMode?: PairTestMode;
}

export function ModelPairRow(props: ModelPairRowProps) {
  const { t } = useTranslation();
  const { selected, model } = props;
  const test = useModelPairTest(selected, model, props.testMode);
  const unset = selected === null || model === "";

  let state: ReactNode;
  if (unset) {
    state = (
      <StateLine
        tone="off"
        word={t("settings.cofferModel.notSet")}
        detail={t("settings.cofferModel.notSetDetail", { text: props.notSet })}
      />
    );
  } else if (test.result?.outcome === "ok") {
    state = <StateLine tone="ok" word={t("settings.cofferModel.answering")} />;
  } else if (test.result?.outcome === "reachable") {
    state = (
      <StateLine
        tone="ok"
        word={t("settings.cofferModel.reachable")}
        detail={t("settings.cofferModel.reachableDetail")}
      />
    );
  } else if (test.result) {
    state = (
      <StateLine
        tone="err"
        word={t("settings.cofferModel.failing")}
        detail={t("settings.cofferModel.failingDetail", {
          error: test.result.message,
          tail: props.failingTail,
        })}
      />
    );
  } else {
    state = <StateLine tone="ok" word={t("settings.cofferModel.set")} />;
  }

  const modelValue = props.offLabel && model === "" ? OFF_VALUE : model;

  return (
    <div>
      <SettingRow label={props.title} description={props.description} status={state} align="start">
        <Select
          // The VALUE is the connection's uid — what the route takes — and the
          // LABEL is its name.
          value={selected?.uid ?? ""}
          onValueChange={props.onProvider}
          disabled={props.providers.length === 0 || props.providerBusy}
        >
          <SelectTrigger className="w-40" aria-label={props.providerLabel}>
            <SelectValue placeholder={props.providerPlaceholder} />
          </SelectTrigger>
          <SelectContent>
            {props.providers.map((p) => (
              <SelectItem key={p.uid} value={p.uid}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={modelValue}
          onValueChange={(m) => props.onModel(m === OFF_VALUE ? null : m)}
          disabled={!selected || props.modelBusy}
        >
          <SelectTrigger className="w-44" aria-label={props.modelLabel}>
            <SelectValue placeholder={props.modelPlaceholder} />
          </SelectTrigger>
          <SelectContent>
            {props.offLabel ? <SelectItem value={OFF_VALUE}>{props.offLabel}</SelectItem> : null}
            {props.options.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          disabled={unset || test.isPending}
          onClick={test.run}
          aria-label={t("settings.cofferModel.testAria", { picker: props.title })}
        >
          {test.isPending ? t("settings.cofferModel.testing") : t("settings.cofferModel.test")}
        </Button>
      </SettingRow>
    </div>
  );
}

function StateLine({
  tone,
  word,
  detail,
}: {
  tone: "ok" | "err" | "off";
  word: string;
  detail?: string;
}) {
  return (
    <span className="flex flex-wrap items-baseline gap-x-1.5 text-xs" data-testid="model-state">
      <StatusWord tone={tone}>{word}</StatusWord>
      {detail ? (
        <span className={tone === "err" ? toneTextClass("error") : "text-text-muted"}>
          {detail}
        </span>
      ) : null}
    </span>
  );
}
