// frontend/src/components/knowledge/KnowledgeBrokenLinks.tsx
//
// A collection's Broken links (spec knowledge "Check every link in a
// collection", "Show a collection as one tree of read-only documents in the
// web UI"): every link Coffer found broken in its files on this read, grouped
// by kind — a link that names no file, one that names several, and one that
// climbs out of the knowledge root. Broken links are all Coffer checks: what
// else a file should carry is the collection's own rules (ADR
// knowledge-collections-own-their-format). Each item names its file by title
// (the path is its tooltip) and opens it. Coffer fixes none of it: Tidy hands
// it to the person's agent, with the rest of the tidy.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut, FindingOut } from "@/lib/api/knowledge";
import { useKnowledgeCheck, useKnowledgeFiles } from "@/lib/hooks/useKnowledge";
import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";

type Kind = FindingOut["kind"];

/** The kinds in the order they are listed. */
const KINDS: Kind[] = ["dead_link", "ambiguous_link", "outside_link"];

/** Items a group lists before "N more". */
const SHOWN = 6;

interface Props {
  collection: CollectionOut;
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
            {finding.target ? (
              <span className="min-w-0 shrink-0 truncate font-mono text-xs text-text-muted">
                {t("knowledge.check.target", { target: finding.target })}
              </span>
            ) : null}
            {finding.others.length > 0 ? (
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

export function KnowledgeBrokenLinks({ collection }: Props) {
  const { t } = useTranslation();
  const check = useKnowledgeCheck(collection.uid);
  const files = useKnowledgeFiles(collection.uid);

  // A file is named by its title once the files are read, by its path until then.
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
    body = KINDS.filter((kind) => of(kind).length > 0).map((kind) => (
      <FindingGroup
        key={kind}
        kind={kind}
        findings={of(kind)}
        uid={collection.uid}
        titleOf={titleOf}
      />
    ));
  }

  return (
    <SettingsSection
      title={t("knowledge.check.title")}
      description={t("knowledge.check.description")}
      testId="knowledge-broken-links"
    >
      {body}
    </SettingsSection>
  );
}
