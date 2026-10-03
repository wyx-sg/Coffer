// src/components/DetailNotFound.tsx — a detail pane whose object is gone (board 1.1.16).
//
// A page-size EmptyState: "This server no longer exists", the id that was
// asked for, two facts — Last seen and Audit, read from the newest audit entry
// that names the object (no entry says so) — and two buttons: Back to the list
// (primary) and View in Activity (outline). One component for every kind;
// the per-kind copy lives in `listStates.kinds.<kind>`.
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Activity, SearchX } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import type { ListKind } from "@/components/ListPaneStates";
import { Button } from "@/components/ui/button";
import { fetchAuditPage } from "@/lib/api/activity";
import { auditListKey } from "@/lib/api/queryKeys";
import { timeAgo } from "@/lib/timeAgo";

interface Props {
  kind: ListKind;
  /** What the address named (a name or a uid). */
  id: string;
  /** The list this detail belongs to. */
  backTo: string;
  icon?: LucideIcon;
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[90px_minmax(0,1fr)] gap-4 border-t border-border-subtle py-[7px]">
      <span className="text-xs text-text-subtle">{label}</span>
      <span className="min-w-0 break-words text-sm text-text">{children}</span>
    </div>
  );
}

export function DetailNotFound({ kind, id, backTo, icon = SearchX }: Props) {
  const { t, i18n } = useTranslation();
  const mono = <span className="font-mono text-xs text-text" />;
  // The newest audit entry that names this object: when it last existed, and what happened.
  const audit = useQuery({
    queryKey: auditListKey({ named: id }),
    queryFn: async () => {
      const page = await fetchAuditPage({ q: id }, 20);
      return page.entries.find((e) => e.resource_name === id) ?? null;
    },
    retry: false,
  });
  const entry = audit.data;
  return (
    <EmptyState
      size="page"
      icon={icon}
      title={t(`listStates.kinds.${kind}.notFoundTitle`)}
      description={
        <Trans
          i18nKey={`listStates.kinds.${kind}.notFoundBody`}
          values={{ id }}
          components={{ mono }}
        />
      }
      action={
        <Button asChild>
          <Link to={backTo}>
            <ArrowLeft aria-hidden /> {t(`listStates.kinds.${kind}.back`)}
          </Link>
        </Button>
      }
      secondaryAction={
        <Button asChild variant="outline">
          <Link to="/activity?tab=changes">
            <Activity aria-hidden /> {t("listStates.notFound.viewInActivity")}
          </Link>
        </Button>
      }
    >
      <div>
        <Fact label={t("listStates.notFound.lastSeen")}>
          {entry
            ? t("listStates.notFound.lastSeenValue", {
                when: timeAgo(entry.timestamp, i18n.language),
                actor: entry.actor,
              })
            : t("listStates.notFound.noRecord")}
        </Fact>
        {entry ? (
          <Fact label={t("listStates.notFound.audit")}>
            <span className="font-mono text-xs">
              {entry.event_type} · {entry.resource_name}
            </span>
          </Fact>
        ) : null}
      </div>
    </EmptyState>
  );
}
