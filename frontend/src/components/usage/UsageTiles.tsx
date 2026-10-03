// src/components/usage/UsageTiles.tsx — the range's headline numbers: estimated cost, input, output, cache read, cache write.
//
// Five tiles in one row, no frame. Cost is always labelled estimated, its "?"
// carries the daemon's note on which prices costed the range, and a range whose
// every request is unpriced reads "—" — never $0.00.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import type { UsageTotals } from "@/lib/api/usage";
import { allUnpriced, formatCost, formatCount, formatTokens } from "@/lib/usage/format";

interface TileProps {
  label: ReactNode;
  value: string;
  note?: string;
}

function Tile({ label, value, note }: TileProps) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
        {label}
      </span>
      <span className="whitespace-nowrap text-[22px] font-bold tracking-[-0.01em] text-text">
        {value}
      </span>
      {note ? <span className="text-xs leading-snug text-text-subtle">{note}</span> : null}
    </div>
  );
}

export function UsageTiles({ totals, priceNote }: { totals: UsageTotals; priceNote: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const costNote = [
    t("usage.tiles.requests", { count: totals.requests, n: formatCount(totals.requests, lang) }),
    totals.unpriced_requests
      ? t("usage.tiles.unpriced", { n: formatCount(totals.unpriced_requests, lang) })
      : null,
    totals.unknown_usage_requests
      ? t("usage.tiles.unknown", { n: formatCount(totals.unknown_usage_requests, lang) })
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const cacheWrite = totals.cache_write_5m_tokens + totals.cache_write_1h_tokens;
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
      <Tile
        label={
          <>
            {t("usage.tiles.cost")}
            <HelpTip label={t("usage.tiles.costHelp")}>
              {/* The daemon's own note on which prices costed this range (server copy). */}
              <p>{priceNote}</p>
            </HelpTip>
          </>
        }
        value={
          allUnpriced(totals) ? t("usage.noPrice") : formatCost(totals.estimated_cost_usd, lang)
        }
        note={costNote}
      />
      <Tile
        label={t("usage.tiles.input")}
        value={formatTokens(totals.input_tokens, lang)}
        note={t("usage.tiles.inputNote")}
      />
      <Tile
        label={t("usage.tiles.output")}
        value={formatTokens(totals.output_tokens, lang)}
        note={t("usage.tiles.outputNote")}
      />
      <Tile
        label={t("usage.tiles.cacheRead")}
        value={formatTokens(totals.cache_read_tokens, lang)}
      />
      <Tile
        label={t("usage.tiles.cacheWrite")}
        value={formatTokens(cacheWrite, lang)}
        note={t("usage.tiles.cacheWriteNote")}
      />
    </div>
  );
}
