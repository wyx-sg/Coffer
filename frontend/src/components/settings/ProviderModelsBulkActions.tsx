// frontend/src/components/settings/ProviderModelsBulkActions.tsx
// The bulk bar for the curated-models table: turn every selected row on or
// off in one write. Lifted out of ProviderModelsTable so that file stays
// within its size budget, the same way McpServersBulkActions is.
import { useTranslation } from "react-i18next";
import { Power, PowerOff } from "lucide-react";

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
  // No reach control here: a curated model is not a Coffer resource and has no
  // per-agent scope — it is one entry of the connection's `models` list, so
  // on/off is the whole of what it can be.
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => apply(true)}>
        <Power className="mr-1.5 size-3.5" /> {t("common.bulk.enable")}
      </Button>
      <Button size="sm" variant="outline" onClick={() => apply(false)}>
        <PowerOff className="mr-1.5 size-3.5" /> {t("common.bulk.disable")}
      </Button>
    </>
  );
}
