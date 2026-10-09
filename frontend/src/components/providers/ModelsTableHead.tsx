// src/components/providers/ModelsTableHead.tsx — the Models table's header: select-all, the switch column, Model · Price · Window · Type.
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";

interface Props {
  /** Every row the filters match is ticked. */
  allOn: boolean;
  /** Some, not all, are ticked. */
  someOn: boolean;
  onToggleAll: () => void;
}

export function ModelsTableHead({ allOn, someOn, onToggleAll }: Props) {
  const { t } = useTranslation();
  return (
    <thead>
      <tr className="border-b border-border-subtle text-xs font-medium text-text-muted">
        <th className="w-10 py-2.5 pl-4 pr-1 font-medium">
          <Checkbox
            checked={allOn}
            indeterminate={someOn}
            aria-label={t("common.bulk.selectAll")}
            onChange={onToggleAll}
          />
        </th>
        <th className="w-14 px-2 py-2.5" aria-hidden />
        <th className="px-2 py-2.5 font-medium">{t("providers.models.cols.model")}</th>
        <th className="w-[24%] px-2 py-2.5 text-right font-medium">
          {t("providers.models.cols.price")}
        </th>
        <th className="w-[120px] px-2 py-2.5 font-medium">{t("providers.models.cols.window")}</th>
        <th className="w-[140px] py-2.5 pl-2 pr-4 font-medium">
          {t("providers.models.cols.type")}
        </th>
      </tr>
    </thead>
  );
}
