// src/components/secret/SecretsBulkBar.tsx — the selection bar, in the place of the filters while secrets are ticked.
//
// "N of M selected", Delete… (outline danger) and Clear. Delete stays offered when some of the
// ticked secrets are in use or waiting: the confirmation skips and names them.
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { SecretsBulkDelete } from "./SecretsBulkDelete";
import type { SecretItem } from "./secretListView";

interface Props {
  selected: SecretItem[];
  /** How many secrets the filters show. */
  total: number;
  onClear: () => void;
}

export function SecretsBulkBar({ selected, total, onClear }: Props) {
  const { t } = useTranslation();
  return (
    <ListSelectionBar
      label={t("secrets.bulk.label")}
      count={selected.length}
      total={total}
      onClear={onClear}
    >
      <SecretsBulkDelete items={selected} onDone={onClear} />
    </ListSelectionBar>
  );
}
