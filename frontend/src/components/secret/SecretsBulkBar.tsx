// src/components/secret/SecretsBulkBar.tsx — the selection bar, in the place of the filters while secrets are ticked.
//
// Select-all covers every secret the filters show (not only the rendered batch). Delete is offered
// only when every ticked secret can go: one in use, or waiting for approval, turns it off and says
// how many stand in the way.
import { useTranslation } from "react-i18next";

import { ListSelectionBar } from "@/components/ListSelectionBar";
import { SecretsBulkDelete } from "./SecretsBulkDelete";
import { isDeletable, type SecretItem } from "./secretListView";

interface Props {
  selected: SecretItem[];
  /** Every secret the filters show is ticked. */
  allChecked: boolean;
  onToggleAll: (on: boolean) => void;
  onClear: () => void;
}

export function SecretsBulkBar({ selected, allChecked, onToggleAll, onClear }: Props) {
  const { t } = useTranslation();
  const blocked = selected.filter((i) => !isDeletable(i)).length;
  return (
    <ListSelectionBar
      label={t("secrets.bulk.label")}
      selectAllLabel={t("secrets.bulk.selectAll")}
      count={selected.length}
      allChecked={allChecked}
      onToggleAll={onToggleAll}
      onClear={onClear}
    >
      <SecretsBulkDelete
        items={selected}
        label={t("common.bulk.delete")}
        disabledReason={blocked > 0 ? t("secrets.bulk.blocked", { count: blocked }) : undefined}
        onDone={onClear}
      />
    </ListSelectionBar>
  );
}
