// frontend/src/components/knowledge/KnowledgeTodoSection.tsx
//
// A collection's To do (spec knowledge "Check a collection mechanically on
// every read", "Show a collection as one tree of read-only documents in the
// web UI"): what Coffer found in its files on this read, grouped by kind and
// listed by what breaks a reader first — dead and ambiguous links, names used
// twice, missing and outdated sources, waiting sources, incomplete pages and
// pages due a recheck (ADR knowledge-stays-current-through-flags-coffer-computes). Each item names its
// page by title (the path is its tooltip) and opens it. Pages without sources
// and pages nothing links to are worth knowing but rarely urgent, so they are
// folded into one line until opened. Coffer fixes none of it: Tidy hands it
// to the person's agent, with the rest of the tidy.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight } from "lucide-react";

import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut, FindingOut } from "@/lib/api/knowledge";
import { useKnowledgeCheck, useKnowledgeFiles } from "@/lib/hooks/useKnowledge";
import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";

type Kind = FindingOut["kind"];

/** The kinds shown open, in the order they are listed: what breaks a reader first. */
const URGENT: Kind[] = [
  "dead_link",
  "ambiguous_link",
  "duplicate_slug",
  "missing_source",
  "superseded_source",
  "waiting_source",
  "incomplete_page",
  "stale_page",
];

/** The kinds folded into one line until opened. */
const MINOR: Kind[] = ["unsourced_page", "orphan_page"];

/** Items a group lists before "N more". */
const SHOWN = 6;

interface Props {
  collection: CollectionOut;
}

/** What a finding names, after the page: the link, slug or keys it concerns. */
function FindingDetail({
  finding,
  titleOf,
}: {
  finding: FindingOut;
  titleOf: (path: string) => string;
}) {
  const { t } = useTranslation();
  let text: string | null = null;
  if (finding.kind === "stale_page") {
    text = finding.target
      ? t("knowledge.check.lastChecked", { date: finding.target })
      : t("knowledge.check.neverChecked");
  } else if (finding.kind === "superseded_source") {
    const newest = finding.others[0];
    text = t("knowledge.check.replaced", {
      target: finding.target,
      newest: newest ? titleOf(newest) : "",
    });
  } else if (finding.target) {
    const key = finding.kind === "incomplete_page" ? "missing" : "target";
    text = t(`knowledge.check.${key}`, { target: finding.target });
  }
  if (!text) return null;
  const mono = finding.kind !== "stale_page" && finding.kind !== "superseded_source";
  return (
    <span
      className={`min-w-0 shrink-0 truncate text-xs text-text-muted ${mono ? "font-mono" : ""}`}
    >
      {text}
    </span>
  );
}

function FindingGroup({
  kind,
  findings,
  uid,
  titleOf,
}: {
  kind: Kind;
  findings: FindingOut[];
  uid: string;
  titleOf: (path: string) => string;
}) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const shown = all ? findings : findings.slice(0, SHOWN);
  return (
    <div className="border-t border-border-subtle py-2.5 first:border-t-0">
      <h3 className="flex items-baseline gap-2 text-sm font-medium text-text">
        {t(`knowledge.check.kinds.${kind}`)}
        <span className="text-xs font-normal text-text-muted">{findings.length}</span>
      </h3>
      <ul className="mt-1 flex flex-col gap-0.5">
        {shown.map((finding, i) => (
          <li
            key={`${finding.path}-${finding.target ?? ""}-${i}`}
            className="flex min-w-0 items-baseline gap-2 text-sm"
          >
            <Link
              to={collectionPath(uid, finding.path)}
              title={pathInCollection(finding.path)}
              className="min-w-0 truncate text-text hover:underline"
            >
              {titleOf(finding.path)}
            </Link>
            <FindingDetail finding={finding} titleOf={titleOf} />
            {finding.others.length > 0 && kind !== "superseded_source" ? (
              <span className="min-w-0 truncate text-xs text-text-muted">
                {t("knowledge.check.others", { paths: finding.others.map(titleOf).join(", ") })}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {findings.length > SHOWN ? (
        <button
          type="button"
          onClick={() => setAll(!all)}
          className="mt-1 text-xs font-label text-accent-text hover:underline"
        >
          {all
            ? t("knowledge.check.fewer")
            : t("knowledge.check.more", { count: findings.length - SHOWN })}
        </button>
      ) : null}
    </div>
  );
}

export function KnowledgeTodoSection({ collection }: Props) {
  const { t } = useTranslation();
  const check = useKnowledgeCheck(collection.uid);
  const files = useKnowledgeFiles(collection.uid);
  const [minorOpen, setMinorOpen] = useState(false);

  // A page is named by its title once the contents are read, by its path until then.
  const titles = new Map((files.data ?? []).map((f) => [f.path, f.title]));
  const titleOf = (path: string) => titles.get(path) || pathInCollection(path);

  let body;
  if (check.isPending) {
    body = (
      <div className="space-y-2 py-2" aria-busy>
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  } else if (check.error) {
    body = (
      <LoadErrorRow
        title={t("knowledge.check.failed")}
        error={check.error}
        onRetry={() => void check.refetch()}
      />
    );
  } else if (check.data.findings.length === 0) {
    body = <p className="py-2 text-sm text-text-muted">{t("knowledge.check.none")}</p>;
  } else {
    const findings = check.data.findings;
    const of = (kind: Kind) => findings.filter((f) => f.kind === kind);
    const urgent = URGENT.filter((kind) => of(kind).length > 0);
    const minor = MINOR.filter((kind) => of(kind).length > 0);
    body = (
      <>
        {urgent.map((kind) => (
          <FindingGroup
            key={kind}
            kind={kind}
            findings={of(kind)}
            uid={collection.uid}
            titleOf={titleOf}
          />
        ))}
        {minor.length > 0 ? (
          <div className="border-t border-border-subtle py-2.5 first:border-t-0">
            <button
              type="button"
              aria-expanded={minorOpen}
              onClick={() => setMinorOpen(!minorOpen)}
              className="flex items-center gap-1.5 text-sm text-text-muted hover:text-text"
            >
              {minorOpen ? (
                <ChevronDown className="size-3.5" aria-hidden />
              ) : (
                <ChevronRight className="size-3.5" aria-hidden />
              )}
              {minor
                .map((kind) => `${t(`knowledge.check.kinds.${kind}`)} ${of(kind).length}`)
                .join(" · ")}
            </button>
            {minorOpen ? (
              <div className="mt-1 pl-5">
                {minor.map((kind) => (
                  <FindingGroup
                    key={kind}
                    kind={kind}
                    findings={of(kind)}
                    uid={collection.uid}
                    titleOf={titleOf}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </>
    );
  }

  return (
    <SettingsSection
      title={t("knowledge.check.title")}
      description={t("knowledge.check.description")}
      testId="knowledge-todo"
    >
      {body}
    </SettingsSection>
  );
}
