// src/components/usage/UsageTiles.tsx — the range's headline numbers, unboxed in one row: estimated cost, input, output, cache read, cache write.
//
// Cost is always labelled estimated, and a range whose every request is
// unpriced reads "—" — never $0.00. The "N model(s) unpriced" fact lives only
// here, as a link to the model on its provider, where its price is set.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { HelpTip } from "@/components/HelpTip";
import type { UsageTotals } from "@/lib/api/usage";
import { allUnpriced, formatCost, formatCount, formatTokens } from "@/lib/usage/format";

interface TileProps {
  label: ReactNode;
  value: string;
  note?: ReactNode;
}

function Tile({ label, value, note }: TileProps) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-text-muted">
        {label}
      </span>
      <span className="whitespace-nowrap text-[22px] font-bold leading-tight tracking-[-0.01em] text-text">
        {value}
      </span>
      {note ? <span className="text-xs leading-snug text-text-subtle">{note}</span> : null}
    </div>
  );
}

interface Props {
  totals: UsageTotals;
  /** The models in the range with no known price; `to` opens the first one on its provider. */
  unpriced: { count: number; to: string } | null;
}

export function UsageTiles({ totals, unpriced }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const cacheWrite = totals.cache_write_5m_tokens + totals.cache_write_1h_tokens;
  const costNote = (
    <>
      {[
        t("usage.tiles.requests", {
          count: totals.requests,
          n: formatCount(totals.requests, lang),
        }),
        totals.unknown_usage_requests
          ? t("usage.tiles.unknown", { n: formatCount(totals.unknown_usage_requests, lang) })
          : null,
      ]
        .filter(Boolean)
        .join(" · ")}
      {unpriced ? (
        <>
          {" · "}
          <Link
            to={unpriced.to}
            className="whitespace-nowrap font-label text-accent-text hover:underline"
          >
            {t("usage.tiles.unpriced", { count: unpriced.count })}
          </Link>
        </>
      ) : null}
    </>
  );
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
      <Tile
        label={
          <>
            {t("usage.tiles.cost")}
            <HelpTip>{t("usage.tiles.costHelp")}</HelpTip>
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
