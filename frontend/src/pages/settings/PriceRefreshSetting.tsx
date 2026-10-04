// frontend/src/pages/settings/PriceRefreshSetting.tsx
//
// "Refresh model prices" in Settings › General, under Coffer's model (spec
// provider-switching "Refresh the bundled price list in the background"). The
// canvas has no price settings of its own, so the one switch lives here: on,
// the daemon fetches genai-prices' published price list once a day; off, it
// prices from the list shipped with this release — for a firewalled Mac. The
// line under it says which list is in use and when its data is from.
import { useTranslation } from "react-i18next";

import { SettingRow } from "@/components/settings/SettingsLayout";
import { Switch } from "@/components/ui/switch";
import { usePriceList, useSetPriceRefresh } from "@/lib/hooks/useProviderPrices";
import { formatPriceDate } from "@/lib/providers/priceDate";

const ID = "price-refresh";

export function PriceRefreshSetting() {
  const { t, i18n } = useTranslation();
  const list = usePriceList();
  const set = useSetPriceRefresh();
  const doc = list.data;
  const updated = formatPriceDate(doc?.updated, i18n.language) ?? t("settings.prices.unknownDate");
  const status = doc
    ? [
        t(`settings.prices.origin.${doc.origin}`, { date: updated }),
        doc.pinned_off ? t("settings.prices.pinnedOff") : null,
        doc.refresh && !doc.pinned_off && doc.last_error ? t("settings.prices.lastFailed") : null,
      ]
        .filter(Boolean)
        .join(" · ")
    : null;
  return (
    <SettingRow
      label={t("settings.prices.label")}
      labelFor={ID}
      description={t("settings.prices.description")}
      status={status ? <span className="text-xs text-text-muted">{status}</span> : undefined}
    >
      <Switch
        id={ID}
        checked={doc?.refresh ?? true}
        disabled={!doc || set.isPending || doc.pinned_off}
        onCheckedChange={(on) => set.mutate(on)}
      />
    </SettingRow>
  );
}
