// frontend/src/components/memory/MemoryAuditLog.tsx
//
// This kind's audit log (spec memory FR-062), the first consumer of
// `useAudit` (lib/hooks/useAudit.ts previously had none). Every lifecycle act
// — aggregation, organise, each override, delivery installed or removed —
// is audited (FR-063); this renders that trail read-only.
import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useMemoryAuditLog } from "@/kinds/memory/useMemory";

/** Compact one-line rendering of an entry's `details` blob — there is no
 * fixed shape across the six memory event types, so this just lists its
 * own key: value pairs rather than special-casing each one. */
function detailsSummary(details: Record<string, unknown> | null | undefined): string {
  if (!details) return "";
  return Object.entries(details)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.length : String(v)}`)
    .join(", ");
}

export function MemoryAuditLog() {
  const { t } = useTranslation();
  const { entries, isPending, error } = useMemoryAuditLog();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t("memory.audit.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : error ? (
          <p className="text-sm text-destructive">{t("memory.audit.loadFailed")}</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("memory.audit.empty")}</p>
        ) : (
          <ul className="space-y-2" data-testid="memory-audit-log">
            {entries.map((e) => (
              <li
                key={e.id}
                className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border/60 pb-2 text-sm last:border-0"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="outline">
                    {t(`memory.audit.events.${e.event_type}`, { defaultValue: e.event_type })}
                  </Badge>
                  <span className="text-muted-foreground">
                    {t(`audit.actor.${e.actor}`, { defaultValue: e.actor })}
                  </span>
                  {e.resource_name ? (
                    <span className="font-mono text-xs text-muted-foreground">
                      {e.resource_name}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>{detailsSummary(e.details)}</span>
                  <span>{new Date(e.timestamp).toLocaleString()}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
