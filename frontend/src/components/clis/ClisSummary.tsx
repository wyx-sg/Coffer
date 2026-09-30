// src/components/clis/ClisSummary.tsx — the one-line strip over the CLIs list: counts per status, and when they were checked.
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import type { Cli } from "@/lib/api/clis";
import { CLI_STATUSES, cliTone, countByStatus, oldestCheck, relativeTime } from "@/lib/clis/format";

export function ClisSummary({ items }: { items: readonly Cli[] }) {
  const { t, i18n } = useTranslation();
  const counts = countByStatus(items);
  const checked = oldestCheck(items);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1" data-testid="clis-summary">
      {CLI_STATUSES.filter((s) => counts[s] > 0).map((s) => (
        <StatusWord key={s} tone={cliTone(s)}>
          {t(`clis.summary.${s}`, { count: counts[s] })}
        </StatusWord>
      ))}
      {checked ? (
        <span className="ml-auto text-xs text-text-muted">
          {t("clis.checkedAgo", { when: relativeTime(checked, i18n.language) })}
        </span>
      ) : null}
    </div>
  );
}
