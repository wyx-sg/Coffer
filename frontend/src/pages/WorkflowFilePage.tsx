// frontend/src/pages/WorkflowFilePage.tsx — one file a run reads or wrote
// (spec workflow "Read a run's files from the app, bounded").
//
// A page and not a dialog. A dialog is for something you answer and dismiss;
// a file a task produced is something you READ — you scroll it, you come back
// to it, you send someone the link. It gets a URL for the same reason the
// task's conversation does, and `?path=` rather than a path segment because
// what it addresses has slashes in it and is not a route of its own.
//
// The path is the run's to validate, not this page's: the daemon guards it
// segment by segment and refuses anything that is not this run's to read, so
// a hand-edited URL gets a refusal rather than a file.
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileQuestion } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { RunFileView } from "@/components/workflow/RunFileView";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useWorkflowRunFile } from "@/lib/hooks/useWorkflowRun";
import { formatBytes } from "@/lib/utils";

export function WorkflowFilePage() {
  const { t } = useTranslation();
  const { runId = "" } = useParams<{ runId: string }>();
  const [params] = useSearchParams();
  const path = params.get("path");
  const { data, isPending, error } = useWorkflowRunFile(runId, path);

  const back = { to: `/runs/${runId}?tab=context`, label: t("workflow.context.backToRun") };

  if (path === null) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={t("workflow.context.fileNotFound")} />
      </div>
    );
  }

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-64" />} />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={path} />
        <EmptyState
          icon={FileQuestion}
          title={t("workflow.context.fileNotFound")}
          description={error ? translateApiError(t, error) : undefined}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        back={back}
        title={data.name}
        subtitle={data.path}
        badges={
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{formatBytes(data.size)}</Badge>
            {data.truncated ? (
              <Badge variant="secondary">{t("workflow.context.truncated")}</Badge>
            ) : null}
          </div>
        }
      />

      <div className="rounded-md border border-border bg-card p-5">
        <RunFileView runId={runId} path={path} />
      </div>
    </div>
  );
}
