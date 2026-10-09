// frontend/src/components/knowledge/KnowledgeCheckSection.tsx
//
// A collection's Check section (spec knowledge "Show a collection as one tree
// of read-only documents in the web UI", "Check a collection mechanically on
// every read"): the findings Coffer computed from its files on this read,
// grouped by kind under a human name, each naming the file it concerns and
// opening it — or one line saying nothing was found. Coffer fixes none of
// them: the person does in their editor, or hands the check to their agent
// (Check with agent, in the pane bar).
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { LoadErrorRow } from "@/components/LoadErrorRow";
import { SettingsSection } from "@/components/settings/SettingsLayout";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut, FindingOut } from "@/lib/api/knowledge";
import { useKnowledgeCheck } from "@/lib/hooks/useKnowledge";
import { collectionPath, pathInCollection } from "@/lib/knowledge/routes";

/** The kinds in the order they are listed: what breaks a reader first. */
const KINDS: FindingOut["kind"][] = [
  "dead_link",
  "ambiguous_link",
  "duplicate_slug",
  "missing_source",
  "incomplete_page",
  "unsourced_page",
  "orphan_page",
  "waiting_source",
];

interface Props {
  collection: CollectionOut;
}

export function KnowledgeCheckSection({ collection }: Props) {
  const { t } = useTranslation();
  const check = useKnowledgeCheck(collection.uid);

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
    body = KINDS.filter((kind) => findings.some((f) => f.kind === kind)).map((kind) => {
      const group = findings.filter((f) => f.kind === kind);
      return (
        <div key={kind} className="border-t border-border-subtle py-2.5 first:border-t-0">
          <h3 className="flex items-baseline gap-2 text-sm font-medium text-text">
            {t(`knowledge.check.kinds.${kind}`)}
            <span className="text-xs font-normal text-text-muted">{group.length}</span>
          </h3>
          <ul className="mt-1 flex flex-col gap-0.5">
            {group.map((finding, i) => (
              <li
                key={`${finding.path}-${finding.target ?? ""}-${i}`}
                className="flex min-w-0 items-baseline gap-2 text-xs"
              >
                <Link
                  to={collectionPath(collection.uid, finding.path)}
                  className="min-w-0 truncate font-mono text-text hover:underline"
                >
                  {pathInCollection(finding.path)}
                </Link>
                {finding.target ? (
                  <span className="shrink-0 font-mono text-text-muted">
                    {t("knowledge.check.target", { target: finding.target })}
                  </span>
                ) : null}
                {finding.others.length > 0 ? (
                  <span className="min-w-0 truncate font-mono text-text-muted">
                    {t("knowledge.check.others", {
                      paths: finding.others.map(pathInCollection).join(", "),
                    })}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      );
    });
  }

  return (
    <SettingsSection
      title={t("knowledge.check.title")}
      description={t("knowledge.check.description")}
      testId="knowledge-check"
    >
      {body}
    </SettingsSection>
  );
}
