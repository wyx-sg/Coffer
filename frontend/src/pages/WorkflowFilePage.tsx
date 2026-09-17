// frontend/src/pages/WorkflowFilePage.tsx — one file a run reads or wrote
// (spec workflow, FR-064).
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
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileQuestion } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useWorkflowRunFile } from "@/lib/hooks/useWorkflowRun";
import { formatBytes } from "@/lib/utils";

/** Markdown is rendered; everything else is shown as it is written. A `.py`
 *  put through a prose renderer would lose its indentation, and a note the
 *  developer wrote in Markdown shown as source would be the raw asterisks. */
function isMarkdown(name: string): boolean {
  return /\.(md|markdown)$/i.test(name);
}

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

      {data.text === null || data.text === undefined ? (
        // Honest rather than mojibake: the daemon says when the bytes are not
        // text, and a preview that rendered them anyway would claim to have
        // shown the developer something.
        <EmptyState
          icon={FileQuestion}
          title={t("workflow.context.notTextTitle")}
          description={t("workflow.context.notText")}
        />
      ) : isMarkdown(data.name) ? (
        <div className="rounded-md border border-border bg-card p-5">
          <Markdown>{data.text}</Markdown>
        </div>
      ) : (
        <pre className="overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted p-4 font-mono text-xs">
          {data.text}
        </pre>
      )}

      {/* The run is where this file belongs; the header's back link is the
          way out, and this is the way out for someone who scrolled. */}
      <Link to={back.to} className="inline-block text-sm text-muted-foreground hover:underline">
        {back.label}
      </Link>
    </div>
  );
}
