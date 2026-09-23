// frontend/src/pages/settings/UpkeepSettings.tsx
//
// Settings → Engine: the work Coffer does when nobody asked it to.
//
// Three passes run on a timer — aggregation reads the agents' own memory into
// the derived tree (spec memory "Aggregate on an interval and on demand"),
// distil lets the model rewrite that derived digest ("Distil incrementally in
// two stages"), and curation reads the knowledge sources the user writes and
// derives the topic documents agents read (spec knowledge "Curate through a
// fenced four-tool pass").
// Until now none of them was visible: two had no switch at all, the third's
// switch could only be changed by editing a synced settings document, and all
// three intervals were constants compiled into the workers. Something that
// writes your files on a timer should be something you can see and stop, which
// is the whole reason this card exists.
//
// Each row says what its pass actually WRITES, because that is the difference
// that matters between them. All three write derived files that deleting and
// re-running reproduces — curation in particular may not touch a source at all
// — so all three ship ON. Curation's row carries the note it does because
// switching it off is what leaves the lane an agent reads empty forever: it is
// the only path from a source to something an agent can read.
//
// Curation's row carries one more thing the other two have no use for: the
// machine allowed to run it. A pass that derives documents must run on exactly
// one machine once a vault spans several, and the machine that owns it was
// until now readable nowhere in the product — including when it names a
// machine the registry no longer holds, which stops curation everywhere
// without saying so. `CurationOwner` is that row's footer.
//
// Edits auto-save, like every other settings surface here (no Save button):
// the switch persists on toggle, the interval on selection.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CalendarClock } from "lucide-react";

import { CurationOwner } from "@/components/settings/CurationOwner";
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
 *  distilled; knowledge is curated on its own schedule. */
const PASSES: UpkeepPass[] = ["aggregate", "distil", "curate"];

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
  footer,
}: {
  pass: UpkeepPass;
  setting: UpkeepSetting;
  onChange: (next: { enabled?: boolean; interval_s?: number | null }) => void;
  busy: boolean;
  /** Rendered full-width under the row. Curation uses it for the machine that
   *  owns the pass: a fact about WHERE it runs, which does not belong in the
   *  column that says how often or the one that says whether. */
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const switchId = `upkeep-${pass}`;

  return (
    <div className="border-t py-4 first:border-t-0 first:pt-0">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <Label htmlFor={switchId} className="text-sm font-medium">
            {t(`settings.upkeep.passes.${pass}.name`)}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t(`settings.upkeep.passes.${pass}.writes`)}
          </p>
          {pass === "curate" ? (
            <p className="text-xs text-status-warn">{t("settings.upkeep.passes.curate.caution")}</p>
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
      {footer}
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
              // Only curation names a machine, and only curation can afford
              // to: the pass rewrites derived documents, so two machines
              // running it fold the same sources into two documents git then
              // merges as two perfectly good additions.
              footer={
                pass === "curate" ? (
                  <CurationOwner ownerId={config?.curate_owner_machine_id ?? null} />
                ) : undefined
              }
            />
          ) : null;
        })}
      </CardContent>
    </Card>
  );
}
