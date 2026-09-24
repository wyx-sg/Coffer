// frontend/src/pages/settings/ExperimentalFeaturesSettings.tsx
//
// Settings → General: which experimental features are switched on on this
// machine (spec experimental-features "List and switch the features on the
// General tab").
//
// One row per registered feature, in the daemon's registry order: its name,
// what it is, whether it is on, and which layer decided that — a
// `COFFER_FEATURES` pin, this machine's own setting, or the build channel's
// default. A pinned feature's switch is disabled; the daemon would refuse the
// write anyway (409 FEATURE_PINNED), and a switch that moves and snaps back
// teaches nothing.
//
// Same rhythm as the daemon card above it: the switch moves at once, settles
// on what the daemon answers, and a failed write puts it back and shows the
// error beside the row that caused it.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { translateApiError } from "@/lib/api/errors";
import { useFeatureList, useSetFeature, type Feature } from "@/lib/hooks/useFeatures";

export function ExperimentalFeaturesSettings() {
  const { t } = useTranslation();
  const { data, error } = useFeatureList();
  const save = useSetFeature();
  // What a click asked for, shown until the daemon answers.
  const [pending, setPending] = useState<Record<string, boolean>>({});
  // The last failed write, kept beside the row it belongs to.
  const [failed, setFailed] = useState<{ key: string; error: unknown } | null>(null);

  const toggle = (feature: Feature, enabled: boolean) => {
    setFailed(null);
    setPending((p) => ({ ...p, [feature.key]: enabled }));
    const settle = () =>
      setPending((p) => {
        const rest = { ...p };
        delete rest[feature.key];
        return rest;
      });
    save.mutate(
      { key: feature.key, enabled },
      {
        onSuccess: settle,
        onError: (err) => {
          settle();
          setFailed({ key: feature.key, error: err });
        },
      },
    );
  };

  const nameOf = (key: string) => t(`settings.features.names.${key}`, { defaultValue: key });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.features.title")}</CardTitle>
        <p className="text-sm text-muted-foreground">
          {data
            ? t("settings.features.subtitle", {
                channel: t(`settings.features.channel.${data.channel}`),
              })
            : null}
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {error ? (
          <p className="text-sm text-destructive">{translateApiError(t, error)}</p>
        ) : !data ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : (
          data.features.map((feature) => {
            const checked = pending[feature.key] ?? feature.enabled;
            const pinned = feature.source === "pin";
            const name = nameOf(feature.key);
            return (
              <div key={feature.key} className="space-y-1" data-testid={`feature-${feature.key}`}>
                <div className="flex items-center justify-between gap-4">
                  <div className="space-y-0.5">
                    <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {name}
                      <Badge variant="outline" className="font-normal">
                        {checked ? t("settings.features.on") : t("settings.features.off")}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {t(`settings.features.descriptions.${feature.key}`, { defaultValue: "" })}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {t(`settings.features.source.${feature.source}`, {
                        channel: t(`settings.features.channel.${data.channel}`),
                      })}
                    </p>
                  </div>
                  <Switch
                    checked={checked}
                    disabled={pinned || feature.key in pending}
                    onCheckedChange={(next) => toggle(feature, next)}
                    aria-label={name}
                  />
                </div>
                {failed?.key === feature.key ? (
                  <p role="alert" className="text-sm text-destructive">
                    {translateApiError(t, failed.error)}
                  </p>
                ) : null}
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
