// frontend/src/components/knowledge/KnowledgeVersionPanel.tsx
//
// What a History row opens into (boards 5.1.05, 5.1.06; Foundations 0.6.05):
// a segmented control — Changes in this version (against the version before)
// or Compare with current (this version against the document as it is now) —
// and, on the right, Restore this version, then the diff with its long lines
// wrapped. The newest version is the current one and offers no restore. A
// restore writes a NEW version naming you, so it is itself in History and can
// be undone the same way; once done the button reads "Restored as a new
// version".
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { DocumentVersionOut } from "@/lib/api/knowledge";
import { whenLabel } from "@/lib/knowledge/changes";
import { diffLines } from "@/lib/knowledge/lineDiff";
import { parseUnifiedDiff } from "@/lib/knowledge/unifiedDiff";
import { useRestoreVersion, useVersionBody, useVersionDiff } from "@/lib/hooks/useKnowledgeHistory";

interface Props {
  path: string;
  version: DocumentVersionOut;
  isCurrent: boolean;
  currentBody: string;
}

type Mode = "changes" | "current";

export function KnowledgeVersionPanel({ path, version, isCurrent, currentBody }: Props) {
  const { t, i18n } = useTranslation();
  const c = version.change;
  const [mode, setMode] = useState<Mode>("changes");
  const diff = useVersionDiff(path, c.version);
  const body = useVersionBody(path, c.version, mode === "current" && !version.removed);
  const restore = useRestoreVersion();
  const { toast } = useToast();
  const [restored, setRestored] = useState(false);
  const againstCurrent = useMemo(
    () => (body.data ? diffLines(body.data.body, currentBody) : []),
    [body.data, currentBody],
  );

  return (
    <div
      role="region"
      aria-label={t("knowledge.history.versionLabel")}
      className="flex flex-col gap-2.5"
    >
      <div className="flex items-center gap-2">
        <Segmented<Mode>
          value={mode}
          onChange={setMode}
          label={t("knowledge.history.diffMode")}
          options={[
            { value: "changes", label: t("knowledge.history.changesInVersion") },
            { value: "current", label: t("knowledge.history.compareCurrent") },
          ]}
        />
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
        ) : (
          <KnowledgeDiff rows={parseUnifiedDiff(diff.data.diff)} />
        )
      ) : version.removed ? (
        <p className="text-sm text-text-subtle">{t("knowledge.history.removedVersion")}</p>
      ) : body.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : body.error ? (
        <p role="alert" className="text-sm text-danger">
          {translateApiError(t, body.error)}
        </p>
      ) : (
        <KnowledgeDiff rows={againstCurrent} />
      )}
    </div>
  );
}
