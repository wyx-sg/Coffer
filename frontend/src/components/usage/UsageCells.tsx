// src/components/usage/UsageCells.tsx — the Cost and Requests cells of a usage row, with their "not the whole story" markers.
//
// A row whose every request is unpriced reads "—" (never $0.00), with a note
// saying why and where a price is set, as its tooltip and its accessible name; a
// partly priced row shows its cost with a marker saying what is left out; a
// row with requests cut before their usage arrived says so beside its count.
import { useTranslation } from "react-i18next";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { UsageTotals } from "@/lib/api/usage";
import { allUnpriced, formatCost, formatCount } from "@/lib/usage/format";

function Marked({ text, tip, label }: { text: string; tip: string; label?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          aria-label={label}
          className="cursor-help underline decoration-text-subtle decoration-dotted underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          {text}
        </span>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  );
}

export function CostCell({ totals }: { totals: UsageTotals }) {
  const { t, i18n } = useTranslation();
  if (allUnpriced(totals)) {
    const tip = t("usage.table.noPriceTip");
    return <Marked text={t("usage.noPrice")} tip={tip} label={tip} />;
  }
  const cost = formatCost(totals.estimated_cost_usd, i18n.language);
  if (totals.unpriced_requests > 0) {
    return (
      <Marked
        text={`${cost}*`}
        tip={t("usage.table.partlyPricedTip", {
          count: totals.unpriced_requests,
          n: formatCount(totals.unpriced_requests, i18n.language),
        })}
      />
    );
  }
  return <>{cost}</>;
}

export function RequestsCell({ totals }: { totals: UsageTotals }) {
  const { t, i18n } = useTranslation();
  const n = formatCount(totals.requests, i18n.language);
  if (totals.unknown_usage_requests === 0) return <>{n}</>;
  return (
    <Marked
      text={`${n}*`}
      tip={t("usage.table.unknownTip", {
        count: totals.unknown_usage_requests,
        n: formatCount(totals.unknown_usage_requests, i18n.language),
      })}
    />
  );
}
