// src/components/providers/ModelsBulkBar.tsx — the Models table's selection bar: Turn on · Turn off for the ticked models.
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { BulkOnOffActions } from "@/components/BulkOnOffActions";

interface Props {
  count: number;
  total: number;
  onClear: () => void;
  /** A write is running. */
  busy: boolean;
  /** How many ticked models are off / on. */
  offCount: number;
  onCount: number;
  onSet: (on: boolean) => void;
}

export function ModelsBulkBar({ count, total, onClear, busy, offCount, onCount, onSet }: Props) {
  const { t } = useTranslation();
  return (
    <ListSelectionBar
      label={t("providers.models.bulkLabel")}
      count={count}
      total={total}
      onClear={onClear}
    >
      <BulkOnOffActions
        busy={busy}
        offCount={offCount}
        onCount={onCount}
        onTurnOn={() => onSet(true)}
        onTurnOff={() => onSet(false)}
      />
    </ListSelectionBar>
  );
}
