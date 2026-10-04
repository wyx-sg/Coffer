// frontend/src/components/mcp/ServerTimeoutFields.tsx — the per-server
// timeouts, one above the other (boards Mcp-EditStdio / Mcp-Edit): Start timeout
// (stdio only — an HTTP server is not started) and Request timeout.
//
// Measured across one vault, average call latency spanned three orders of
// magnitude between servers (9ms to 10.9s), so one default cannot fit all.
// Bounds mirror `domain/mcp/server_config.py` exactly; the inputs constrain
// what the backend would reject anyway.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BOUNDS, type Timeouts } from "@/lib/mcp/serverTimeouts";

interface Props {
  value: Timeouts;
  onChange: (next: Timeouts) => void;
  idPrefix: string;
  /** Show Start timeout (a stdio server); off for HTTP. */
  showSpawn?: boolean;
}

export function ServerTimeoutFields({ value, onChange, idPrefix, showSpawn = true }: Props) {
  const { t } = useTranslation();
  const fields = [
    ...(showSpawn
      ? [
          {
            key: "spawn" as const,
            labelKey: "mcp.timeouts.spawn",
            hintKey: "mcp.timeouts.spawnHint",
          },
        ]
      : []),
    {
      key: "request" as const,
      labelKey: "mcp.timeouts.request",
      hintKey: "mcp.timeouts.requestHint",
    },
  ];
  return (
    <div className="flex flex-col gap-4">
      {fields.map((f) => (
        <div key={f.key} className="space-y-1.5">
          <Label htmlFor={`${idPrefix}-${f.key}`}>{t(f.labelKey)}</Label>
          <div className="relative w-[120px]">
            <Input
              id={`${idPrefix}-${f.key}`}
              type="number"
              inputMode="numeric"
              className="pr-7 font-mono [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
              min={BOUNDS[f.key].min}
              max={BOUNDS[f.key].max}
              value={value[f.key]}
              onChange={(e) => {
                const n = Number(e.target.value);
                onChange({ ...value, [f.key]: Number.isFinite(n) ? n : value[f.key] });
              }}
            />
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 right-2.5 flex items-center font-mono text-sm text-text-muted"
            >
              {t("mcp.timeouts.unit")}
            </span>
          </div>
          <p className="text-xs text-text-muted">{t(f.hintKey)}</p>
        </div>
      ))}
    </div>
  );
}
