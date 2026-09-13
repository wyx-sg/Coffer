// frontend/src/components/settings/ProviderModelsColumns.tsx
// The curated-models table's three columns — id, type, on/off — built from the
// row callbacks the table owns. Lifted out of ProviderModelsTable so that file
// stays within its size budget; the state and the writes stay there.
import { useTranslation } from "react-i18next";

import { type Column } from "@/components/DataTable";
import { ModalitySelect } from "@/components/settings/ModalitySelect";
import { Switch } from "@/components/ui/switch";
import type { Modality, ProviderModel } from "@/lib/api/providers";

export function useProviderModelColumns(opts: {
  modalityOf: (row: ProviderModel) => Modality;
  isOn: (id: string) => boolean;
  toggle: (row: ProviderModel) => void;
  setModality: (row: ProviderModel, modality: Modality) => void;
  pending: boolean;
}): Column<ProviderModel>[] {
  const { t } = useTranslation();
  const { modalityOf, isOn, toggle, setModality, pending } = opts;
  return [
    {
      key: "model",
      header: t("settings.connections.detail.modelId"),
      cell: (m) => <span className="font-mono text-xs">{m.id}</span>,
    },
    {
      key: "modality",
      header: t("settings.connections.detail.modality"),
      cell: (m) => (
        <ModalitySelect
          value={modalityOf(m)}
          onChange={(v) => setModality(m, v)}
          disabled={pending}
          label={m.id}
        />
      ),
    },
    {
      key: "status",
      header: t("resources.cols.status"),
      className: "text-right",
      cell: (m) => (
        <Switch
          checked={isOn(m.id)}
          onCheckedChange={() => toggle(m)}
          disabled={pending}
          aria-label={`${t("resources.cols.status")}: ${m.id}`}
        />
      ),
    },
  ]
}
