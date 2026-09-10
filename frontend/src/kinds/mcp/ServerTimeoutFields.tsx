// frontend/src/kinds/mcp/ServerTimeoutFields.tsx — the three per-server timeouts.
//
// These have been configurable on the backend since spec 001 and had no UI at
// all, so every registered server ran on the defaults. That is a poor fit for
// real upstreams: measured across one vault, average call latency spanned three
// orders of magnitude between servers (9ms to 10.9s), and the slowest routinely
// ran past 60s against a 120s default — so a hung call blocked an agent for two
// minutes with no feedback.
//
// Bounds mirror `domain/mcp/server_config.py` exactly; the inputs constrain what
// the backend would reject anyway, so a bad value is caught before the request.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { BOUNDS, type Timeouts } from "./serverTimeouts";

interface Props {
  value: Timeouts;
  onChange: (next: Timeouts) => void;
  idPrefix: string;
}

export function ServerTimeoutFields({ value, onChange, idPrefix }: Props) {
  const { t } = useTranslation();
  const fields = [
    { key: "spawn" as const, labelKey: "mcp.timeouts.spawn", hintKey: "mcp.timeouts.spawnHint" },
    {
      key: "request" as const,
      labelKey: "mcp.timeouts.request",
      hintKey: "mcp.timeouts.requestHint",
    },
    { key: "idle" as const, labelKey: "mcp.timeouts.idle", hintKey: "mcp.timeouts.idleHint" },
  ];
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-medium">{t("mcp.timeouts.legend")}</legend>
      <div className="grid grid-cols-3 gap-3">
        {fields.map((f) => (
          <div key={f.key} className="space-y-1.5">
            <Label htmlFor={`${idPrefix}-${f.key}`} className="text-xs">
              {t(f.labelKey)}
            </Label>
            <Input
              id={`${idPrefix}-${f.key}`}
              type="number"
              inputMode="numeric"
              min={BOUNDS[f.key].min}
              max={BOUNDS[f.key].max}
              value={value[f.key]}
              onChange={(e) => {
                const n = Number(e.target.value);
                onChange({ ...value, [f.key]: Number.isFinite(n) ? n : value[f.key] });
              }}
            />
            <p className="text-[11px] text-muted-foreground">{t(f.hintKey)}</p>
          </div>
        ))}
      </div>
    </fieldset>
  );
}
