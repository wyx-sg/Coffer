// src/components/change-preview/ChangeSummary.tsx
// The summary line: "4 changes in 2 agents" (or "… and Coffer") at 13/550, then one op chip per kind present with its number.
import { useTranslation } from "react-i18next";

import { OpChip } from "./OpChip";
import { OP_ORDER, countByOp, groupByAgent, type ChangeItem } from "@/lib/changePreview/changeCounts";

interface Props {
  items: readonly ChangeItem[];
}

export function ChangeSummary({ items }: Props) {
  const { t } = useTranslation();
  const counts = countByOp(items);
  const groups = groupByAgent(items);
  // Coffer's own item (an import adding servers to it) is not an agent.
  const withCoffer = groups.some((g) => g.agentType === "coffer");
  const agents = groups.length - (withCoffer ? 1 : 0);
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1.5" data-testid="change-summary">
      <span className="text-sm font-label text-text">
        {t(withCoffer ? "changePreview.summaryWithCoffer" : "changePreview.summary", {
          changes: t("changePreview.changes", { count: items.length }),
          agents: t("changePreview.agents", { count: agents }),
        })}
      </span>
      {OP_ORDER.filter((op) => counts[op] > 0).map((op) => (
        <span key={op} className="inline-flex items-center gap-1.5" data-op-count={op}>
          <OpChip op={op} />
          <span className="text-xs text-text-muted">{counts[op]}</span>
        </span>
      ))}
    </div>
  );
}
