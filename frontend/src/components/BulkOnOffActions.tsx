// src/components/BulkOnOffActions.tsx — Turn on · Turn off inside a ListSelectionBar, for every list of switchable rows.
//
// MCP tools, resources and prompts, a custom tool group's tools and a
// provider's models share it. Each button acts on the ticked rows whose state
// it would change, and is disabled when there are none.
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

interface Props {
  /** A bulk write is running. */
  busy: boolean;
  /** How many ticked rows are off / on: what Turn on / Turn off would change. */
  offCount: number;
  onCount: number;
  onTurnOn: () => void;
  onTurnOff: () => void;
}

export function BulkOnOffActions({ busy, offCount, onCount, onTurnOn, onTurnOff }: Props) {
  const { t } = useTranslation();
  return (
    <>
      <Button size="sm" variant="outline" disabled={busy || offCount === 0} onClick={onTurnOn}>
        {t("common.bulk.turnOn")}
      </Button>
      <Button size="sm" variant="outline" disabled={busy || onCount === 0} onClick={onTurnOff}>
        {t("common.bulk.turnOff")}
      </Button>
    </>
  );
}
