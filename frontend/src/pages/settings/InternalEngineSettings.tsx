// pages/settings/InternalEngineSettings.tsx — the "Coffer's engine" picker of the
// Coffer's model section (spec internal-engine "Show and change Coffer's model
// in Settings › General").
//
// Coffer's own passes — distilling agents' memory, curating knowledge — run on
// the connection flagged `internal_default` (endpoint + key) with the model
// chosen here. Both live apart from the chat agents: the connection is the
// global flag, the model a separate singleton.
//
// Under the picker sits the bound on ONE call to that model (spec
// internal-engine "Carry the bound on one model call"). It belongs beside the
// model rather than with the upkeep rows because it is a property of the
// ENDPOINT, not of any one pass: the same number bounds a distil pass, a
// knowledge description, each turn of curation and a transcription. A pass
// that runs out of time defers its work and reports success, so a bound set
// below what the endpoint really takes leaves the layer converging at a
// fraction of its rate with nothing looking broken.
//
// The row's line is the short answer; what a call covers and why the bound
// should sit above the provider's real latency is behind the "?" beside the
// label. Edits auto-save, like every other settings surface here (no Save button).
import { useTranslation } from "react-i18next";
import { RotateCcw } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { HelpTip } from "@/components/HelpTip";
import { ModelPairRow } from "@/components/settings/cofferModel/ModelPairRow";
import { Button } from "@/components/ui/button";
import { SettingRow } from "@/components/settings/SettingsLayout";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useConnectionModelOptions } from "@/lib/hooks/useConnectionModelOptions";
import {
  useInternalEngineConfig,
  useSetInternalEngineModel,
  useSetModelTimeout,
} from "@/lib/hooks/useInternalEngine";
import { useProviders, useSetInternalDefaultProvider } from "@/lib/hooks/useProviders";

/** The bounds offered, in seconds. Every one is inside the range the server
 *  accepts (5–600), so the dropdown cannot compose a refusal; the short end is
 *  for a local model that either answers at once or is wedged, the long end for
 *  a gateway that thinks for minutes. */
const TIMEOUT_CHOICES = [15, 30, 60, 120, 300, 600];

/** `null` is "the built-in bound" — the server tells us what that is, so the
 *  option can name it rather than showing a blank. */
const DEFAULT_VALUE = "default";

type Translate = ReturnType<typeof useTranslation>["t"];

function timeoutLabel(t: Translate, seconds: number): string {
  if (seconds >= 60 && seconds % 60 === 0)
    return t("settings.internalEngine.minutes", { count: seconds / 60 });
  return t("settings.internalEngine.seconds", { count: seconds });
}

export function InternalEngineSettings() {
  const { t } = useTranslation();
  const { data: providers = [], error, refetch } = useProviders();
  const selected = providers.find((p) => p.internal_default) ?? null;
  const setInternalDefault = useSetInternalDefaultProvider();
  const { data: config } = useInternalEngineConfig();
  const setModel = useSetInternalEngineModel();

  // The engine runs a CHAT model, so the list is narrowed to modality `text`;
  // the saved model stays at its head even when the endpoint cannot list it.
  const currentModel = config?.model ?? "";
  const options = useConnectionModelOptions(selected, "text", currentModel);

  if (error) {
    return (
      <EmptyState
        tone="error"
        size="compact"
        title={t("providers.loadFailed")}
        description={translateApiError(t, error)}
        action={
          <Button variant="outline" size="sm" onClick={() => void refetch()}>
            <RotateCcw aria-hidden /> {t("common.retry")}
          </Button>
        }
      />
    );
  }

  return (
    <ModelPairRow
      title={t("settings.cofferModel.engine.title")}
      description={t("settings.cofferModel.engine.description")}
      providers={providers}
      selected={selected}
      onProvider={(uid) => setInternalDefault.mutate(uid)}
      providerBusy={setInternalDefault.isPending}
      providerLabel={t("settings.internalEngine.connection")}
      providerPlaceholder={t("settings.internalEngine.connectionPlaceholder")}
      model={currentModel}
      options={options}
      onModel={(m) => setModel.mutate(m)}
      modelBusy={setModel.isPending}
      modelLabel={t("settings.internalEngine.model")}
      modelPlaceholder={t("settings.internalEngine.modelPlaceholder")}
      notSet={t("settings.cofferModel.engine.notSet")}
      failingTail={t("settings.cofferModel.engine.failingTail")}
    >
      <TimeoutRow />
    </ModelPairRow>
  );
}

function TimeoutRow() {
  const { t } = useTranslation();
  const { data: config } = useInternalEngineConfig();
  const setBound = useSetModelTimeout();
  const timeout = config?.model_timeout_s ?? null;
  const defaultTimeout = config?.default_model_timeout_s;
  // The control renders only once the server has told us its default:
  // offering "Default" without the number it stands for is the blank this
  // control exists to avoid.
  if (defaultTimeout === undefined) return null;
  // A bound written by the CLI need not be one of ours; show it rather than
  // silently reading as something the user did not choose.
  const choices =
    timeout !== null && !TIMEOUT_CHOICES.includes(timeout)
      ? [timeout, ...TIMEOUT_CHOICES].sort((a, b) => a - b)
      : TIMEOUT_CHOICES;

  return (
    <SettingRow
      indent
      label={
        <span className="inline-flex items-center gap-0.5">
          {t("settings.internalEngine.timeout")}
          <HelpTip>{t("settings.internalEngine.timeoutMore")}</HelpTip>
        </span>
      }
      description={t("settings.internalEngine.timeoutHint")}
    >
      <Select
        value={timeout === null ? DEFAULT_VALUE : String(timeout)}
        onValueChange={(v) => setBound.mutate(v === DEFAULT_VALUE ? null : Number(v))}
        disabled={setBound.isPending}
      >
        <SelectTrigger className="w-44" aria-label={t("settings.internalEngine.timeout")}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={DEFAULT_VALUE}>
            {t("settings.internalEngine.defaultTimeout", {
              timeout: timeoutLabel(t, defaultTimeout),
            })}
          </SelectItem>
          {choices.map((s) => (
            <SelectItem key={s} value={String(s)}>
              {timeoutLabel(t, s)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </SettingRow>
  );
}
