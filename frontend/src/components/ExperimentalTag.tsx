// src/components/ExperimentalTag.tsx — the "Experimental" mark beside an experimental feature's page title (Foundations 0.7.05).
//
// 11px, hairline border, text-muted, 16 high; the page header puts it 8px
// after the title. Only the feature's own top page carries it — a detail page
// under it (a memory partition) does not repeat it.
import { useTranslation } from "react-i18next";

export function ExperimentalTag() {
  const { t } = useTranslation();
  return (
    <span className="inline-flex h-4 shrink-0 items-center whitespace-nowrap rounded-[4px] border border-border px-1 text-2xs font-normal leading-none text-text-muted">
      {t("settings.features.experimental")}
    </span>
  );
}
