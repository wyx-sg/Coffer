// frontend/src/components/memory/UnresolvableBadge.tsx
//
// The one mark a partition wears when the repository it is keyed on is no
// longer on disk (spec memory "Report unresolvable partitions"; board 5.2.01):
// a warning dot and the words "Repository missing" — the only coloured status
// on the partitions table. Rendered identically on the list row and on the
// detail header, so the same fact never reads as two different things.
//
// Such a partition is delivered to NOBODY: nothing resolves to it any more, and
// its notes reach no session. That is precisely why it is marked rather than
// filtered out — deleting it is the developer's decision, and a partition
// missing from the list is a decision they can never make.
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";

export function UnresolvableBadge() {
  const { t } = useTranslation();
  return (
    <span data-testid="partition-unresolvable-badge">
      <StatusWord tone="warn">{t("memory.cols.unresolvable")}</StatusWord>
    </span>
  );
}
