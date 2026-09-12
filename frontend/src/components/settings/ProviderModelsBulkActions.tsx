// frontend/src/components/settings/ProviderModelsBulkActions.tsx
// The bulk bar for the curated-models table: turn every selected row on or
// off in one write. Lifted out of ProviderModelsTable so that file stays
// within its size budget, the same way McpServersBulkActions is.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { ProviderModel } from "@/lib/api/providers";

export function ProviderModelsBulkActions({
  rows,
  onApply,
  onDone,
}: {
  rows: ProviderModel[];
  onApply: (rows: ProviderModel[], on: boolean) => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const apply = (on: boolean) => {
    onApply(rows, on);
    onDone();
  };
  return (
    <div className="flex items-center gap-2">
      <Button size="sm" variant="outline" onClick={() => apply(true)}>
        {t("common.bulk.enable")}
      </Button>
      <Button size="sm" variant="outline" onClick={() => apply(false)}>
        {t("common.bulk.disable")}
      </Button>
    </div>
  );
}
