// src/components/overview/RecentActivity.tsx — the last few notable events, each as the Activity page words it.
//
// The five newest audit entries: when and by whom, then the kind, the name
// and the plain-language sentence — the same `describeActivity` the Activity
// page's Changes tab renders, so a line reads the same in both places.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAudit } from "@/lib/hooks/useAudit";
import { kindMeta } from "@/lib/overview/kinds";
import { formatShortTime } from "@/lib/overview/time";
import { describeActivity } from "@/lib/activity/activityText";
import { actorLabel } from "@/lib/activity/recordText";

const LIMIT = 5;

export function RecentActivity() {
  const { t } = useTranslation();
  const audit = useAudit({ limit: LIMIT });
  const entries = audit.data?.entries ?? [];

  return (
    <section aria-labelledby="overview-activity" className="space-y-3">
      <div className="flex items-center gap-2">
        <h2 id="overview-activity" className="text-sm font-semibold">
          {t("overview.activity.title")}
        </h2>
        <Link to="/activity" className="ml-auto text-xs text-accent-text hover:underline">
          {t("overview.activity.open")}
        </Link>
      </div>
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
        <ul
          data-visual-volatile
          className="divide-y divide-border-subtle rounded-xl border border-border-subtle bg-surface-raised"
        >
          {entries.slice(0, LIMIT).map((entry) => {
            const meta = kindMeta(entry.resource_kind);
            return (
              <li
                key={entry.id}
                className="flex flex-col gap-0.5 px-4 py-2.5 md:flex-row md:items-baseline md:gap-3"
              >
                <span className="shrink-0 text-xs text-text-subtle md:w-40">
                  <time dateTime={entry.timestamp}>{formatShortTime(entry.timestamp)}</time>
                  {" · "}
                  {t("overview.activity.by", {
                    actor: actorLabel(t, entry.actor),
                  })}
                </span>
                <span className="min-w-0 text-sm text-text">
                  {entry.resource_kind ? (
                    <span className="mr-1.5 text-text-muted">{t(meta.labelKey)}</span>
                  ) : null}
                  {entry.resource_name ? (
                    <span className="mr-1.5 font-mono text-xs">{entry.resource_name}</span>
                  ) : null}
                  <span className="text-text-muted">{describeActivity(t, entry)}</span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
