// frontend/src/pages/settings/UpkeepSettings.tsx
//
// Settings → Engine: the work Coffer does when nobody asked it to.
//
// Three passes run on a timer — aggregation reads the agents' own memory into
// the derived tree (spec memory FR-007), organise lets the model rewrite that
// derived digest (spec memory FR-017), and tidy lets it rewrite the user's own
// knowledge files (spec knowledge FR-031). Until now none of them was visible:
// two had no switch at all, the third's switch could only be changed by editing
// a synced settings document, and all three intervals were constants compiled
// into the workers. Something that rewrites your files on a timer should be something
// you can see and stop, which is the whole reason this card exists.
//
// Each row says what its pass actually WRITES, because that is the difference
// that matters between them: two rewrite derived files that deleting and
// re-running reproduces, and one rewrites the only copy. That last one is the
// only one that ships off, and the only one whose row carries a warning.
//
// Edits auto-save, like every other settings surface here (no Save button):
// the switch persists on toggle, the interval on selection.
import { useTranslation } from "react-i18next";
import { CalendarClock } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useInternalEngineConfig, useSetUpkeep } from "@/lib/hooks/useInternalEngine";
import type { UpkeepPass, UpkeepSetting } from "@/lib/api/internalEngine";

/** The intervals offered, in seconds. A pass over an idle vault is nearly
 *  free, so the short end is real rather than decorative; the long end is for
 *  a vault whose owner wants the model's hands on their files rarely. */
const INTERVAL_CHOICES = [15 * 60, 30 * 60, 60 * 60, 3 * 60 * 60, 6 * 60 * 60, 12 * 60 * 60, 86400];

/** The passes, in the order they actually run: memory is aggregated, then
 *  organised; knowledge is tidied on its own schedule. */
const PASSES: UpkeepPass[] = ["aggregate", "organise", "tidy"];

/** `null` is "this pass's own default" — the server tells us what that is, so
 *  the option can say so rather than showing a blank. */
const DEFAULT_VALUE = "default";

type Translate = ReturnType<typeof useTranslation>["t"];

function intervalLabel(t: Translate, seconds: number): string {
  if (seconds % 3600 === 0) return t("settings.upkeep.everyHours", { count: seconds / 3600 });
  return t("settings.upkeep.everyMinutes", { count: Math.round(seconds / 60) });
}

function PassRow({
  pass,
  setting,
  onChange,
  busy,
}: {
  pass: UpkeepPass;
  setting: UpkeepSetting;
  onChange: (next: { enabled?: boolean; interval_s?: number | null }) => void;
  busy: boolean;
}) {
  const { t } = useTranslation();
  const switchId = `upkeep-${pass}`;

  return (
    <div className="flex flex-col gap-3 border-t py-4 first:border-t-0 first:pt-0 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1">
        <Label htmlFor={switchId} className="text-sm font-medium">
          {t(`settings.upkeep.passes.${pass}.name`)}
        </Label>
        <p className="text-xs text-muted-foreground">
          {t(`settings.upkeep.passes.${pass}.writes`)}
        </p>
        {pass === "tidy" ? (
          <p className="text-xs text-status-warn">{t("settings.upkeep.passes.tidy.caution")}</p>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <Select
          value={setting.interval_s === null ? DEFAULT_VALUE : String(setting.interval_s)}
          onValueChange={(v) => onChange({ interval_s: v === DEFAULT_VALUE ? null : Number(v) })}
          disabled={busy || !setting.enabled}
        >
          <SelectTrigger
            className="w-40"
            aria-label={t("settings.upkeep.interval", {
              pass: t(`settings.upkeep.passes.${pass}.name`),
            })}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={DEFAULT_VALUE}>
              {t("settings.upkeep.defaultInterval", {
                interval: intervalLabel(t, setting.default_interval_s),
              })}
            </SelectItem>
            {INTERVAL_CHOICES.map((s) => (
              <SelectItem key={s} value={String(s)}>
                {intervalLabel(t, s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Switch
          id={switchId}
          checked={setting.enabled}
          onCheckedChange={(enabled) => onChange({ enabled })}
          disabled={busy}
          aria-label={t(`settings.upkeep.passes.${pass}.name`)}
        />
      </div>
    </div>
  );
}

export function UpkeepSettings() {
  const { t } = useTranslation();
  const { data: config } = useInternalEngineConfig();
  const setUpkeep = useSetUpkeep();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="size-5 text-primary" strokeWidth={1.5} />
          {t("settings.upkeep.title")}
        </CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">{t("settings.upkeep.subtitle")}</p>
      </CardHeader>
      <CardContent>
        {PASSES.map((pass) => {
          // A pass the server did not report is a pass this build does not
          // know about; skip the row rather than render a broken one.
          const setting = config?.upkeep?.[pass];
          return setting ? (
            <PassRow
              key={pass}
              pass={pass}
              setting={setting}
              busy={setUpkeep.isPending}
              onChange={(next) => setUpkeep.mutate({ pass, ...next })}
            />
          ) : null;
        })}
      </CardContent>
    </Card>
  );
}
