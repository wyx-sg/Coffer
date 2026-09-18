// pages/settings/InternalEngineSettings.tsx — the internal-engine selection
// (spec provider-switching amendment 2026-06-22b). Coffer's own LLM engine — the knowledge curation
// pass, and whatever else Coffer runs itself — uses whichever connection is picked here
// (endpoint + key) with the model chosen here. Both live apart from the chat
// agents: the connection is the global `internal_default`, the model is a
// separate singleton. Replaces the per-card star toggle that used to set it.
//
// The third control is the bound on ONE call to that model (spec
// internal-engine FR-022). It belongs beside the model rather than in the
// upkeep card because it is a property of the ENDPOINT, not of any one pass:
// the same number bounds the memory distil pass, a knowledge description, each
// turn of curation and a transcription. It is here for a failure that does not
// look like one — a pass that runs out of time defers its work and reports
// success, so a bound set below what the endpoint really takes leaves the
// layer converging at a fraction of its rate with nothing looking broken.
//
// It is Coffer's own configuration, not a resource served to agents, so it sits
// under Settings → Engine and reads the connection list itself rather than
// taking it from a resource page above.
//
// Edits auto-save, like every other settings surface here (no Save button).
import { useTranslation } from "react-i18next";
import { Cpu } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { translateApiError } from "@/lib/api/errors";
import { useProviders, useSetInternalDefaultProvider } from "@/lib/hooks/useProviders";
import {
  useInternalEngineConfig,
  useSetInternalEngineModel,
  useSetModelTimeout,
} from "@/lib/hooks/useInternalEngine";
import { useConnectionModelOptions } from "@/lib/hooks/useConnectionModelOptions";

/** The bounds offered, in seconds. Every one is inside the range the server
 *  accepts (5–600), so the dropdown cannot compose a refusal; the short end is
 *  for a local model that either answers at once or is wedged, the long end for
 *  a gateway that thinks for minutes. */
const TIMEOUT_CHOICES = [15, 30, 60, 120, 300, 600];

/** `null` is "the built-in bound" — the server tells us what that is, so the
 *  option can name it rather than showing a blank (as the upkeep card's
 *  interval does). */
const DEFAULT_VALUE = "default";

type Translate = ReturnType<typeof useTranslation>["t"];

function timeoutLabel(t: Translate, seconds: number): string {
  if (seconds >= 60 && seconds % 60 === 0)
    return t("settings.internalEngine.minutes", { count: seconds / 60 });
  return t("settings.internalEngine.seconds", { count: seconds });
}

export function InternalEngineSettings() {
  const { t } = useTranslation();
  const { data: providers = [], isPending, error } = useProviders();
  const selected = providers.find((p) => p.internal_default) ?? null;
  const setInternalDefault = useSetInternalDefaultProvider();
  const { data: config } = useInternalEngineConfig();
  const setModel = useSetInternalEngineModel();
  const setBound = useSetModelTimeout();

  // The internal engine runs a CHAT model, so the list is narrowed to modality
  // `text`; the saved model stays at its head even when the endpoint cannot
  // list it.
  const currentModel = config?.model ?? "";
  const options = useConnectionModelOptions(selected, "text", currentModel);

  const timeout = config?.model_timeout_s ?? null;
  const defaultTimeout = config?.default_model_timeout_s;
  // A bound written by the CLI need not be one of ours; show it rather than
  // silently reading as something the user did not choose.
  const timeoutChoices =
    timeout !== null && !TIMEOUT_CHOICES.includes(timeout)
      ? [timeout, ...TIMEOUT_CHOICES].sort((a, b) => a - b)
      : TIMEOUT_CHOICES;

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-6">{t("common.loading")}</CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardContent className="py-6 text-destructive">{translateApiError(t, error)}</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cpu className="size-5 text-primary" strokeWidth={1.5} />
          {t("settings.internalEngine.title")}
        </CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("settings.internalEngine.subtitle")}
        </p>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>{t("settings.internalEngine.connection")}</Label>
          <Select
            // The VALUE is the connection's uid — what the route takes — and the
            // LABEL is its name.
            value={selected?.uid ?? ""}
            onValueChange={(uid) => setInternalDefault.mutate(uid)}
            disabled={providers.length === 0 || setInternalDefault.isPending}
          >
            <SelectTrigger aria-label={t("settings.internalEngine.connection")}>
              <SelectValue placeholder={t("settings.internalEngine.connectionPlaceholder")} />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.uid} value={p.uid}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid gap-1.5">
          <Label>{t("settings.internalEngine.model")}</Label>
          <Select
            value={currentModel}
            onValueChange={(m) => setModel.mutate(m)}
            disabled={!selected || setModel.isPending}
          >
            <SelectTrigger aria-label={t("settings.internalEngine.model")}>
              <SelectValue placeholder={t("settings.internalEngine.modelPlaceholder")} />
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

        {/* The timeout renders only once the server has told us its default:
            offering "Default" without the number it stands for is the blank
            this control exists to avoid. */}
        {defaultTimeout === undefined ? null : (
          <div className="grid gap-1.5 sm:col-span-2">
            <Label>{t("settings.internalEngine.timeout")}</Label>
            <Select
              value={timeout === null ? DEFAULT_VALUE : String(timeout)}
              onValueChange={(v) => setBound.mutate(v === DEFAULT_VALUE ? null : Number(v))}
              disabled={setBound.isPending}
            >
              <SelectTrigger
                className="w-full sm:w-56"
                aria-label={t("settings.internalEngine.timeout")}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DEFAULT_VALUE}>
                  {t("settings.internalEngine.defaultTimeout", {
                    timeout: timeoutLabel(t, defaultTimeout),
                  })}
                </SelectItem>
                {timeoutChoices.map((s) => (
                  <SelectItem key={s} value={String(s)}>
                    {timeoutLabel(t, s)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {t("settings.internalEngine.timeoutHint")}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
