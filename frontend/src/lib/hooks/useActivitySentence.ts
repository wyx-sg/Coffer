// src/lib/hooks/useActivitySentence.ts — an audit row's sentence, secrets named as they are now.
//
// An audit row points at a secret by its minted ref; the sentence names it by
// the label a person gave it, read from the same list the Secrets page shows.
import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";

import { describeActivity } from "@/lib/activity/activityText";
import { useSecrets } from "@/lib/hooks/useSecrets";
import type { components } from "@/lib/api/types";

type AuditEntry = components["schemas"]["AuditEntryOut"];

export function useActivitySentence(): (entry: AuditEntry) => string {
  const { t } = useTranslation();
  const rows = useSecrets().data?.refs;
  const labels = useMemo(
    () => (rows ? new Map(rows.map((r) => [r.ref, r.label ?? null])) : undefined),
    [rows],
  );
  return useCallback((entry) => describeActivity(t, entry, labels), [t, labels]);
}
