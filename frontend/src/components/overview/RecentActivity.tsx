// src/components/overview/RecentActivity.tsx — the last few notable events, each as the Activity page words it.
//
// The four newest audit entries: when and by whom, then the kind, the name
// and the plain-language sentence — the same `describeActivity` the Activity
// page's Changes tab renders, so a line reads the same in both places.
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAudit } from "@/lib/hooks/useAudit";
import { kindMeta } from "@/lib/overview/kinds";
import { formatShortTime } from "@/lib/overview/time";
import { Section } from "@/components/Section";
import { describeActivity } from "@/lib/activity/activityText";
import { actorLabel } from "@/lib/activity/recordText";

// Four across one card, as the board lays them out.
const LIMIT = 4;

export function RecentActivity() {
  const { t } = useTranslation();
  const audit = useAudit({ limit: LIMIT });
  const entries = audit.data?.entries ?? [];

  return (
    <Section
      as="h2"
      gap="snug"
      labelled
      title={t("overview.activity.title")}
      actions={
        <Link
          to="/activity"
          className="inline-flex items-center gap-1 rounded-xs text-xs font-label text-accent-text hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          {t("overview.activity.open")}
          <ArrowRight className="size-3" aria-hidden />
        </Link>
      }
    >
      {audit.isPending ? (
        <div aria-busy className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-4 w-full max-w-md" />
          ))}
        </div>
      ) : audit.isError ? (
        <p className="text-xs text-danger">{translateApiError(t, audit.error)}</p>
      ) : entries.length === 0 ? (
        <p className="text-sm text-text-muted">{t("overview.activity.empty")}</p>
      ) : (
        // Which entries a fresh daemon writes first varies; screenshot tests mask it.
        // One card, the entries side by side, newest first (board 1.3.01).
        <ul
          data-visual-volatile
          className="grid grid-cols-1 divide-y divide-border-subtle rounded-xl border border-border bg-surface-raised md:grid-cols-4 md:divide-x md:divide-y-0"
        >
          {entries.slice(0, LIMIT).map((entry) => {
            const meta = kindMeta(entry.resource_kind);
            const KindIcon = meta.icon;
            const sentence = [
              entry.resource_kind ? t(meta.labelKey) : "",
              entry.resource_name ?? "",
              describeActivity(t, entry),
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <li key={entry.id} className="flex min-w-0 flex-col gap-1 px-4 py-3">
                <span className="flex items-center gap-1.5 text-2xs text-text-subtle">
                  <KindIcon className="size-3 shrink-0" aria-hidden />
                  <span className="truncate">
                    <time dateTime={entry.timestamp}>{formatShortTime(entry.timestamp)}</time>
                    {" · "}
                    {t("overview.activity.by", { actor: actorLabel(t, entry.actor) })}
                  </span>
                </span>
                <span className="truncate text-xs text-text" title={sentence}>
                  {entry.resource_kind ? <span className="mr-1">{t(meta.labelKey)}</span> : null}
                  {entry.resource_name ? (
                    <span className="mr-1 font-mono text-2xs">{entry.resource_name}</span>
                  ) : null}
                  <span className="text-text-muted">{describeActivity(t, entry)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
