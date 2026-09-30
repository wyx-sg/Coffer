// frontend/src/components/knowledge/KnowledgeVersionPanel.tsx
//
// One version of a document on its History tab: who and when, what it did,
// its diff against the version before, a link to the whole curation pass when
// it was one, and Restore this version — a new version naming you, so the
// restore is itself in History and can be undone the same way.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { RotateCcw } from "lucide-react";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import type { DocumentVersionOut } from "@/lib/api/knowledge";
import { changeSentence, writerLabel } from "@/lib/knowledge/changes";
import { changePath } from "@/lib/knowledge/routes";
import { parseUnifiedDiff } from "@/lib/knowledge/unifiedDiff";
import { useRestoreVersion, useVersionDiff } from "@/lib/hooks/useKnowledgeHistory";
import { formatDateTime } from "@/lib/utils";

interface Props {
  path: string;
  version: DocumentVersionOut;
  isCurrent: boolean;
}

export function KnowledgeVersionPanel({ path, version, isCurrent }: Props) {
  const { t } = useTranslation();
  const c = version.change;
  const diff = useVersionDiff(path, c.version);
  const restore = useRestoreVersion();

  return (
    <section className="space-y-3" aria-label={t("knowledge.history.versionLabel")}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm">
          <span className="font-semibold">{formatDateTime(c.time)}</span>
          <span className="text-text-subtle"> · {writerLabel(t, c)}</span>
        </p>
        <div className="ml-auto flex items-center gap-2">
          {c.operation === "pass" ? (
            <Button variant="ghost" size="sm" asChild>
              <Link to={changePath(c.version)}>{t("knowledge.history.wholePass")}</Link>
            </Button>
          ) : null}
          {!isCurrent && !version.removed ? (
            <Button
              variant="outline"
              size="sm"
              disabled={restore.isPending}
              onClick={() => restore.mutate({ path, version: c.version })}
            >
              <RotateCcw aria-hidden /> {t("knowledge.history.restore")}
            </Button>
          ) : null}
        </div>
      </div>
      <p className="text-sm text-text-muted">{changeSentence(t, c)}</p>
      {diff.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : diff.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, diff.error)}
        </p>
      ) : (
        <KnowledgeDiff rows={parseUnifiedDiff(diff.data.diff)} />
      )}
    </section>
  );
}
