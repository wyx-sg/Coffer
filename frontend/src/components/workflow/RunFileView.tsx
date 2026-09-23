// frontend/src/components/workflow/RunFileView.tsx
// One file out of a run's directory, rendered.
//
// Shared by the file's own page and by the panel beside a task's conversation,
// because "show me this file" is one question and two answers to it would
// eventually disagree about which ones are markdown and which are images.
//
// Three shapes, decided by the daemon and the name rather than by guessing:
// text that is markdown is rendered, other text is shown as it was written,
// and bytes the daemon says are not text are either an image — fetched through
// the daemon, because an <img> cannot carry the token it authorises by — or
// honestly reported as something this app will not pretend to show.
import { useTranslation } from "react-i18next";
import { FileQuestion } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Markdown } from "@/components/Markdown";
import { Skeleton } from "@/components/ui/skeleton";
import { translateApiError } from "@/lib/api/errors";
import { useRunImages } from "@/lib/hooks/useRunImages";
import { useWorkflowRunFile } from "@/lib/hooks/useWorkflowRun";

/** Markdown is rendered; everything else is shown as it is written. A `.py`
 *  put through a prose renderer would lose its indentation, and a note the
 *  developer wrote in Markdown shown as source would be the raw asterisks. */
function isMarkdown(name: string): boolean {
  return /\.(md|markdown)$/i.test(name);
}

function isImage(name: string): boolean {
  return /\.(png|jpe?g|gif|webp|avif)$/i.test(name);
}

interface Props {
  runId: string;
  /** Relative to the run's own directory. */
  path: string;
}

export function RunFileView({ runId, path }: Props) {
  const { t } = useTranslation();
  const { data, isPending, error } = useWorkflowRunFile(runId, path);
  // An image has no text to preview, so it is fetched as bytes. Asked for by
  // the same markdown syntax a note uses, so one hook answers both.
  const images = useRunImages(runId, isImage(path) ? `![](${path})` : "");

  if (isPending) return <Skeleton className="h-64 w-full" />;
  if (error || !data) {
    return (
      <EmptyState
        icon={FileQuestion}
        title={t("workflow.context.fileNotFound")}
        description={error ? translateApiError(t, error) : undefined}
      />
    );
  }

  if (data.text === null || data.text === undefined) {
    const source = images[path];
    if (source !== undefined) {
      return <img src={source} alt={data.name} className="max-w-full rounded-md" />;
    }
    // Honest rather than mojibake: the daemon says when the bytes are not
    // text, and a preview that rendered them anyway would claim to have shown
    // the developer something.
    return (
      <EmptyState
        icon={FileQuestion}
        title={t("workflow.context.notTextTitle")}
        description={t("workflow.context.notText")}
      />
    );
  }

  if (isMarkdown(data.name)) {
    return <Markdown>{data.text}</Markdown>;
  }
  return (
    <pre className="overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
      {data.text}
    </pre>
  );
}
