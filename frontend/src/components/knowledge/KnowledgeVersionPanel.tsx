// frontend/src/components/knowledge/KnowledgeVersionPanel.tsx
//
// One version of a document on its History tab (boards 5.1.03, 5.1.21): who
// and when, what it did — for a curation pass, how many documents the pass
// changed and a link to the whole pass — and one of two diffs, chosen by a
// segmented control: Changes in this version (against the version before)
// or Compare with current (this version against the document as it is now).
// An older version offers Restore this version — a new version naming you, so
// the restore is itself in History and can be undone the same way; once done
// the button reads "Restored as a new version".
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { RotateCcw } from "lucide-react";

import { KnowledgeDiff } from "@/components/knowledge/KnowledgeDiff";
import { KnowledgeWriterMark } from "@/components/knowledge/KnowledgeWriterMark";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { translateApiError } from "@/lib/api/errors";
import type { DocumentVersionOut } from "@/lib/api/knowledge";
import { versionSentence, whenLabel, writerLabel } from "@/lib/knowledge/changes";
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

const STATUS_SIGN = { added: "+", modified: "~", removed: "−" } as const;

export function KnowledgeVersionPanel({ path, version, isCurrent, currentBody }: Props) {
  const { t, i18n } = useTranslation();
  const c = version.change;
  const [mode, setMode] = useState<Mode>("changes");
  const diff = useVersionDiff(path, c.version);
  const body = useVersionBody(path, c.version, mode === "current" && !version.removed);
  const restore = useRestoreVersion();
  const { toast } = useToast();
  const [restored, setRestored] = useState(false);
  const isPass = c.operation === "pass";
  const doc = c.documents.find((d) => d.path === path);
  const againstCurrent = useMemo(
    () => (body.data ? diffLines(body.data.body, currentBody) : []),
    [body.data, currentBody],
  );
  const name = path.split("/").pop() ?? path;

  return (
    <section
      aria-label={t("knowledge.history.versionLabel")}
      className="flex min-h-0 min-w-0 flex-1 flex-col gap-3.5 overflow-auto px-6 py-[18px]"
    >
      <div className="flex items-start gap-2.5">
        <span className="pt-0.5">
          <KnowledgeWriterMark writer={c.writer} agent={c.agent} />
        </span>
        <div className="flex min-w-0 flex-col gap-[3px]">
          <p className="text-md font-bold">
            {whenLabel(t, c.time, i18n.language)} · {writerLabel(t, c)}
          </p>
          <p className="text-xs leading-[1.45] text-text-muted">
            {versionSentence(t, c)}
            {isPass ? (
              <>
                {". "}
                {t("knowledge.history.oneOfPass", { count: c.documents.length })}{" "}
                <Link to={changePath(c.version)} className="font-label text-text hover:underline">
                  {t("knowledge.history.wholePass")}
                </Link>
              </>
            ) : !isCurrent ? (
              <>
                {". "}
                {t("knowledge.history.restoreHint")}
              </>
            ) : null}
          </p>
        </div>
        {!isCurrent && !version.removed ? (
          <span className="ml-auto flex shrink-0 gap-1.5">
            {restored ? (
              <span className="text-xs text-text-muted">{t("knowledge.history.restored")}</span>
            ) : (
              <Button
                variant="outline"
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
                <RotateCcw aria-hidden /> {t("knowledge.history.restore")}
              </Button>
            )}
          </span>
        ) : null}
      </div>

      <Segmented<Mode>
        value={mode}
        onChange={setMode}
        label={t("knowledge.history.diffMode")}
        className="self-start"
        options={[
          { value: "changes", label: t("knowledge.history.changesInVersion") },
          { value: "current", label: t("knowledge.history.compareCurrent") },
        ]}
      />

      <div className="flex items-center gap-2">
        <span className="whitespace-nowrap font-mono text-xs">{name}</span>
        {doc ? (
          <span className="inline-flex h-5 items-center gap-1 rounded-sm bg-chip px-1.5 text-2xs font-label text-text-muted">
            <span className="font-mono">{STATUS_SIGN[doc.status]}</span>
            {t(`knowledge.pass.status.${doc.status}`)}
          </span>
        ) : null}
        {doc && mode === "changes" ? (
          <span className="ml-auto flex gap-1.5 font-mono text-2xs">
            {doc.added ? <span className="text-success">+{doc.added}</span> : null}
            {doc.removed ? <span className="text-danger">−{doc.removed}</span> : null}
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
    </section>
  );
}
