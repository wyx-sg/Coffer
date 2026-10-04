// frontend/src/pages/sync/SyncRoundCadence.tsx
//
// "Run a round": how often this Mac syncs, or only when the user presses
// Sync now. One control over two stored fields (see syncRemoteForm): a
// cadence is `interval_seconds` with `enabled: true`; "Only when I press Sync
// now" is `enabled: false`, the interval kept for when a cadence is picked
// again. An interval set elsewhere (the CLI) that matches no preset is shown
// as its own "every N minutes" option rather than rounded to one.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CADENCES, cadenceLabel } from "./syncRemoteForm";

const MANUAL = "manual";

interface Props {
  id: string;
  intervalSeconds: number;
  enabled: boolean;
  onChange: (next: { intervalSeconds: number; enabled: boolean }) => void;
  disabled?: boolean;
  describedBy?: string;
}

export function SyncRoundCadence({
  id,
  intervalSeconds,
  enabled,
  onChange,
  disabled,
  describedBy,
}: Props) {
  const { t } = useTranslation();
  const presets: number[] = [...CADENCES];
  const options = presets.includes(intervalSeconds)
    ? presets
    : [...presets, intervalSeconds].sort((a, b) => a - b);

  return (
    <Select
      value={enabled ? String(intervalSeconds) : MANUAL}
      disabled={disabled}
      onValueChange={(v) =>
        onChange(
          v === MANUAL
            ? { intervalSeconds, enabled: false }
            : { intervalSeconds: Number(v), enabled: true },
        )
      }
    >
      <SelectTrigger id={id} aria-describedby={describedBy}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((seconds) => (
          <SelectItem key={seconds} value={String(seconds)}>
            {cadenceLabel(t, seconds)}
          </SelectItem>
        ))}
        <SelectItem value={MANUAL}>{t("sync.remote.cadence.manual")}</SelectItem>
      </SelectContent>
    </Select>
  );
}
