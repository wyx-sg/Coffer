// frontend/src/components/memory/MemoryAutomaticPopover.tsx
//
// Memory's "Automatic · hourly" control (design 5.2.11): whether Coffer reads
// the agents' memory on its own, and how often. It sits in the Memory header
// and the partition header, beside Update memory.
//
// One switch, two passes. Reading the agents' memory is two passes on the
// daemon — `aggregate` reads their files into the derived tree, `distil` turns
// what was read into memories — and a person asks one question of them: does
// Coffer keep my memory current on its own? So the switch sets both, and the
// interval is the read's (`aggregate`): distilling follows whatever was read,
// on its own timer. "Last read · next in" is the read's too.
import { useTranslation } from "react-i18next";

import { AutomaticPopover, clockLine } from "@/components/upkeep/AutomaticPopover";
import { useInternalEngineConfig, useSetUpkeep } from "@/lib/hooks/useInternalEngine";

export function MemoryAutomaticPopover() {
  const { t, i18n } = useTranslation();
  const { data: config } = useInternalEngineConfig();
  const setUpkeep = useSetUpkeep();
  const read = config?.upkeep?.aggregate;
  if (!read) return null;
  const distil = config?.upkeep?.distil;
  // The switch reads on only when both halves are on: a read with no distil
  // keeps nothing new, so it is not "reading automatically".
  const setting = { ...read, enabled: read.enabled && (distil?.enabled ?? true) };

  return (
    <AutomaticPopover
      testId="memory-automatic"
      title={t("memory.automatic.title")}
      description={t("memory.automatic.description")}
      setting={setting}
      busy={setUpkeep.isPending}
      onToggle={(enabled) => {
        setUpkeep.mutate({ pass: "aggregate", enabled });
        if (distil) setUpkeep.mutate({ pass: "distil", enabled });
      }}
      onInterval={(interval_s) => setUpkeep.mutate({ pass: "aggregate", interval_s })}
      clock={clockLine(t, i18n.language, setting, "memory.automatic.last", "memory.automatic.never")}
    />
  );
}
