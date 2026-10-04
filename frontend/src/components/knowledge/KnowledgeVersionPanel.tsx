// frontend/src/components/knowledge/KnowledgeVersionPanel.tsx
//
// The right half of a document's History (boards 5.1.05, 5.1.06; Foundations
// 0.6.05): for the chosen version, a segmented control — Changes in this
// version (against the version before) or Compare with current (this version
// against the document as it is now) — a "See the pass" link when a curation
// pass wrote it, and, on the right, Restore this version, then the document's
// diff as a FileDiff (the one diff renderer: header, op, counts, long lines
// wrapped). The newest version is the current one and offers no restore. A
// restore writes a NEW version naming you, so it is itself in History and can
// be undone the same way; once done the button reads "Restored as a new
// version".
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { FileDiff } from "@/components/change-preview/FileDiff";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { DocumentVersionOut } from "@/lib/api/knowledge";
import type { ChangeItem, ChangeOp, DiffLine } from "@/lib/changePreview/changeCounts";
import { whenLabel } from "@/lib/knowledge/changes";
import { diffLines } from "@/lib/knowledge/lineDiff";
import { changePath } from "@/lib/knowledge/routes";
import { parseUnifiedDiff } from "@/lib/knowledge/unifiedDiff";
import { useRestoreVersion, useVersionBody, useVersionDiff } from "@/lib/hooks/useKnowledgeHistory";

interface Props {
  path: string;
  version: DocumentVersionOut;
  isCurrent: boolean;
  currentBody: string;
}

type Mode = "changes" | "current";

const OP: Record<"added" | "modified" | "removed", ChangeOp> = {
  added: "add",
  modified: "modify",
  removed: "remove",
};

function fileItem(
  path: string,
  op: ChangeOp,
  lines: DiffLine[],
  counts?: { added: number; removed: number },
): ChangeItem {
  return {
    id: path,
    agentType: "coffer",
    path,
    op,
    added: counts?.added ?? lines.filter((l) => l.kind === "add").length,
    removed: counts?.removed ?? lines.filter((l) => l.kind === "remove").length,
    diff: lines,
  };
}

export function KnowledgeVersionPanel({ path, version, isCurrent, currentBody }: Props) {
  const { t, i18n } = useTranslation();
  const c = version.change;
  const [mode, setMode] = useState<Mode>("changes");
  const diff = useVersionDiff(path, c.version);
  const body = useVersionBody(path, c.version, mode === "current" && !version.removed);
  const restore = useRestoreVersion();
  const { toast } = useToast();
  const [restored, setRestored] = useState(false);
  const changesItem = useMemo(
    () =>
      diff.data
        ? fileItem(path, OP[diff.data.status], parseUnifiedDiff(diff.data.diff), {
            added: diff.data.added,
            removed: diff.data.removed,
          })
        : null,
    [diff.data, path],
  );
  const currentItem = useMemo(
    () => (body.data ? fileItem(path, "modify", diffLines(body.data.body, currentBody)) : null),
    [body.data, currentBody, path],
  );

  return (
    <div
      role="region"
      aria-label={t("knowledge.history.versionLabel")}
      className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-auto p-3"
    >
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Segmented<Mode>
          value={mode}
          onChange={setMode}
          label={t("knowledge.history.diffMode")}
          options={[
            { value: "changes", label: t("knowledge.history.changesInVersion") },
            { value: "current", label: t("knowledge.history.compareCurrent") },
          ]}
        />
        {c.operation === "pass" ? (
          <Link
            to={changePath(c.version)}
            className="text-xs font-label text-accent-text hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
          >
            {t("knowledge.history.seePass")}
          </Link>
        ) : null}
        {!isCurrent && !version.removed ? (
          <span className="ml-auto flex shrink-0">
            {restored ? (
              <span className="text-xs text-text-muted">{t("knowledge.history.restored")}</span>
            ) : (
              <Button
                variant="outline"
                size="sm"
                loading={restore.isPending}
                onClick={() =>
                  restore.mutate(
                    { path, version: c.version },
                    {
                      onSuccess: () => {
                        setRestored(true);
                        toast.success(
                          t("knowledge.history.restoredToast", {
                            when: whenLabel(t, c.time, i18n.language),
                          }),
                        );
                      },
                    },
                  )
                }
              >
                {t("knowledge.history.restore")}
              </Button>
            )}
          </span>
        ) : null}
      </div>

      {mode === "changes" ? (
        diff.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : diff.error ? (
          <p role="alert" className="text-sm text-danger">
            {translateApiError(t, diff.error)}
          </p>
        ) : changesItem ? (
          <FileDiff item={changesItem} showEmpty />
        ) : null
      ) : version.removed ? (
        <p className="text-sm text-text-subtle">{t("knowledge.history.removedVersion")}</p>
      ) : body.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : body.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, body.error)}
        </p>
      ) : currentItem ? (
        <FileDiff item={currentItem} showEmpty />
      ) : null}
    </div>
  );
}
