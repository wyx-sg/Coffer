// frontend/src/pages/settings/ExperimentalFeaturesSettings.tsx
//
// Settings → Features: the experimental features and the switch for each (spec
// experimental-features "Switch a feature from the settings page or over REST"). The tab
// is in every build.
//
// One row per registered feature, in the daemon's registry order: its name and
// an Experimental mark, what it is, the switch, and which layer decided its
// state — a `COFFER_FEATURES` pin, this machine's own setting, or the default
// (off). A pinned feature's switch is disabled; the daemon would refuse the
// write anyway (409 FEATURE_PINNED), and a switch that moves and snaps back
// teaches nothing. A feature with a setting of this machine's own offers
// "Reset to default", which removes the setting.
//
// The switch moves at once, settles on what the daemon answers, and a failed
// write puts it back and says "Couldn’t save the change: <reason>" under the row
// that caused it (canvas 1.4.21, 1.4.22).
import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  SETTINGS_STACK,
  SettingRow,
  SettingsSection,
  SettingsTabHeader,
} from "@/components/settings/SettingsLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import {
  useFeatureList,
  useResetFeature,
  useSetFeature,
  type Feature,
} from "@/lib/hooks/useFeatures";

/** The locale key of the line saying which layer decided a feature's state. */
function sourceKey(feature: Feature, checked: boolean): string {
  if (feature.source !== "setting") return feature.source;
  return checked ? "settingOn" : "settingOff";
}

export function ExperimentalFeaturesSettings() {
  const { t } = useTranslation();
  const { data } = useFeatureList();
  const save = useSetFeature();
  const reset = useResetFeature();
  // What a click asked for, shown until the daemon answers.
  const [pending, setPending] = useState<Record<string, boolean>>({});
  // The last failed write, kept beside the row it belongs to.
  const [failed, setFailed] = useState<{ key: string; error: unknown } | null>(null);

  const settle = (key: string) =>
    setPending((p) => {
      const rest = { ...p };
      delete rest[key];
      return rest;
    });

  const toggle = (feature: Feature, enabled: boolean) => {
    setFailed(null);
    setPending((p) => ({ ...p, [feature.key]: enabled }));
    save.mutate(
      { key: feature.key, enabled },
      {
        onSuccess: () => settle(feature.key),
        onError: (err) => {
          settle(feature.key);
          setFailed({ key: feature.key, error: err });
        },
      },
    );
  };

  const resetToDefault = (feature: Feature) => {
    setFailed(null);
    reset.mutate(feature.key, { onError: (err) => setFailed({ key: feature.key, error: err }) });
  };

  return (
    <div className="flex flex-col gap-5">
      <SettingsTabHeader
        title={t("settings.tabs.features")}
        intro={t("settings.features.subtitle")}
      />
      <div className={SETTINGS_STACK}>
        <SettingsSection testId="experimental-features">
          {!data ? (
            <div className="flex flex-col gap-2 py-3" data-testid="features-loading">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : null}
          {data?.features.map((feature) => {
            const checked = pending[feature.key] ?? feature.enabled;
            const name = t(`settings.features.names.${feature.key}`, { defaultValue: feature.key });
            return (
              <div key={feature.key} data-testid={`feature-${feature.key}`}>
                <SettingRow
                  label={
                    <span className="flex flex-wrap items-center gap-2">
                      {name}
                      <Badge variant="outline" className="font-normal">
                        {t("settings.features.experimental")}
                      </Badge>
                    </span>
                  }
                  description={
                    t(`settings.features.descriptions.${feature.key}`, { defaultValue: "" }) ||
                    undefined
                  }
                  status={
                    <>
                      <span className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                        <span>
                          {t("settings.features.decidedBy")}:{" "}
                          {t(`settings.features.source.${sourceKey(feature, checked)}`)}
                        </span>
                        {feature.source === "setting" ? (
                          <Button
                            type="button"
                            variant="link"
                            size="sm"
                            className="h-auto p-0 text-xs"
                            disabled={reset.isPending || feature.key in pending}
                            onClick={() => resetToDefault(feature)}
                          >
                            {t("settings.features.reset")}
                          </Button>
                        ) : null}
                      </span>
                      {failed?.key === feature.key ? (
                        <p role="alert" className="text-xs text-danger">
                          {t("settings.features.saveFailed", {
                            reason: translateApiError(t, failed.error),
                          })}
                        </p>
                      ) : null}
                    </>
                  }
                >
                  <Switch
                    checked={checked}
                    disabled={feature.source === "pin" || feature.key in pending}
                    onCheckedChange={(next) => toggle(feature, next)}
                    aria-label={name}
                  />
                </SettingRow>
              </div>
            );
          })}
        </SettingsSection>
      </div>
    </div>
  );
}
