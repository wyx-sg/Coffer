// src/components/overview/RecentActivity.tsx — the last few notable events, each as the Activity page words it.
//
// The four newest audit entries: when and by whom, then one sentence in one
// colour — the kind and the name (in mono) when the entry is about a named
// resource, then the plain-language sentence, the same `describeActivity` the
// Activity page's Changes tab renders, so a line reads the same in both places
// (Overview board 1.2.09). A sentence too long for its cell ends in an
// ellipsis with the whole of it on hover. Entries about a resource whose
// experimental feature is switched off are left out, like that feature's pages.
import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { TruncatedText } from "@/components/ui/truncated-text";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useAudit } from "@/lib/hooks/useAudit";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { kindMeta } from "@/lib/overview/kinds";
import { formatShortTime } from "@/lib/overview/time";
import { Section } from "@/components/Section";
import { describeActivity } from "@/lib/activity/activityText";
import { actorLabel } from "@/lib/activity/recordText";

// Four across one card, as the board lays them out; a few more are read so that
// leaving out a switched-off feature's entries still fills the card.
const LIMIT = 4;
const FETCH = 12;

export function RecentActivity() {
  const { t } = useTranslation();
  const audit = useAudit({ limit: FETCH });
  const pageOpen = useKindPageOpen();
  const entries = (audit.data?.entries ?? [])
    .filter((e) => !e.resource_kind || pageOpen(e.resource_kind))
    .slice(0, LIMIT);

  return (
    <Section
      as="h2"
      gap="snug"
      compact
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
        // One card, the entries side by side, newest first (board 1.2.09).
        <ul
          data-visual-volatile
          className="grid grid-cols-1 divide-y divide-border-subtle rounded-xl border border-border bg-surface-raised md:grid-cols-4 md:divide-x md:divide-y-0"
        >
          {entries.map((entry) => {
            const meta = kindMeta(entry.resource_kind);
            const KindIcon = meta.icon;
            const named = entry.resource_kind && entry.resource_name;
            const verbPart = describeActivity(t, entry);
            const sentence = [named ? t(meta.labelKey) : "", entry.resource_name ?? "", verbPart]
              .filter(Boolean)
              .join(" ");
            return (
              <li key={entry.id} className="flex min-w-0 flex-col gap-1 px-4 py-3">
                <span className="flex items-center gap-1.5 text-2xs text-text-subtle">
                  <KindIcon className="size-[13px] shrink-0" aria-hidden />
                  <span className="truncate">
                    <time dateTime={entry.timestamp}>{formatShortTime(entry.timestamp)}</time>
                    {" · "}
                    {t("overview.activity.by", { actor: actorLabel(t, entry.actor) })}
                  </span>
                </span>
                <TruncatedText text={sentence} className="text-xs text-text">
                  {named ? `${t(meta.labelKey)} ` : null}
                  {entry.resource_name ? (
                    <>
                      <span className="font-mono text-2xs">{entry.resource_name}</span>{" "}
                    </>
                  ) : null}
                  {verbPart}
                </TruncatedText>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}
