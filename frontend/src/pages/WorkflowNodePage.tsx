// frontend/src/pages/WorkflowNodePage.tsx — one task's conversation page
// (spec workflow, FR-030/FR-039/FR-045/FR-052).
//
// This is where a run is driven, and it is driven by TALKING (FR-063). There
// is no Retry here and no Skip: they were the last two buttons left over from
// the form the run used to be, and a button that reruns a task is a worse way
// of saying "do that again" than saying it. The task's agent is in the thread;
// what the developer wants is a sentence, and the sentence also stays in the
// transcript that every later task opens with (FR-029), which a button press
// never did.
//
// The one control that survives is the APPROVAL, and it is IN the thread
// rather than over it (FR-039): the agent asking to open a merge request is a
// thing it did in the conversation, so the decision sits under the message
// that led to it. Approving an exact payload by typing "ok" into the composer
// is precisely what the gate exists to prevent, which is why this one is a
// button and the rest are sentences.
//
// The composer is here WHATEVER state the task is in (FR-068), including
// before it has started: what is typed then is the brief the task will open
// with. Where the sentence goes is the one thing this page decides — a task
// whose turn is in flight takes it in its conversation, where it queues for
// the agent already reading; every other state hands it to the engine, which
// decides whether it carries the attempt on or opens the next one.
//
// The page is a WORKSPACE rather than a document — full-bleed, one screen
// tall, the conversation taking every pixel the header does not — because a
// transcript that a run spent hours writing is the content, not an attachment
// to a status header.
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Workflow } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { NodeHeader } from "@/components/workflow/NodeHeader";
import { NodeWorkspace } from "@/components/workflow/NodeWorkspace";
import { translateApiError } from "@/lib/api/errors";
import { useSayToTask, useWorkflowRun } from "@/lib/hooks/useWorkflowRun";
import type { RunDetail } from "@/lib/api/workflow";

/** The node with this key, and the stage it sits in. */
function locate(detail: RunDetail, nodeKey: string) {
  for (const stage of detail.stages) {
    const node = stage.nodes.find((n) => n.key === nodeKey);
    if (node) return { stage, node };
  }
  return null;
}

/** Full-bleed: Layout's main region pads every page and its inner wrapper has
 *  no height, so the padding is cancelled here and the screen height taken
 *  back — the same trick, and for the same reason, as ChatPage. */
const WORKSPACE = "-mx-6 -my-10 flex h-screen flex-col overflow-hidden md:-mx-10";
/** The header, and nothing else, keeps a margin. Everything under it is the
 *  work, and the work runs to the edges. */
const GUTTER = "shrink-0 border-b border-border px-6 py-4 md:px-8";

export function WorkflowNodePage() {
  const { t } = useTranslation();
  const { runId = "", nodeKey = "" } = useParams<{ runId: string; nodeKey: string }>();
  const { data: detail, isPending, error } = useWorkflowRun(runId);
  const say = useSayToTask(runId);

  const back = { to: `/runs/${runId}`, label: t("workflow.nodeConversation.backToRun") };

  if (isPending) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={<Skeleton className="h-8 w-64" />} />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const found = detail ? locate(detail, nodeKey) : null;
  if (error || !detail || !found) {
    return (
      <div className="space-y-6">
        <PageHeader back={back} title={nodeKey} />
        <EmptyState
          icon={Workflow}
          title={t("workflow.nodeConversation.notFound")}
          description={error ? translateApiError(t, error) : undefined}
        />
      </div>
    );
  }

  const { run } = detail;
  const { stage, node } = found;
  const latest = node.latest;

  return (
    <div className={WORKSPACE}>
      <div className={GUTTER}>
        <NodeHeader run={run} stage={stage} node={node} back={back} />

        {latest?.failure_reason ? (
          <p className="pt-2 text-sm text-destructive">
            {t(`workflow.node.failure.${latest.failure_reason}`)}
          </p>
        ) : null}
      </div>

      <NodeWorkspace
        runId={run.id}
        nodeKey={node.key}
        assigned={latest}
        templateAgent={node.agent}
        conversationId={latest?.conversation_id ?? null}
        attemptId={latest?.id}
        ownedHere={run.owned_here}
        started={node.status !== "pending"}
        instructions={latest?.instructions}
        // Only a running task's turn can queue a message; every other state
        // goes to the engine, which decides what the sentence means (FR-068).
        onSay={
          node.status === "running" && latest?.conversation_id
            ? null
            : (text: string) => say.mutate({ nodeKey: node.key, text })
        }
        saying={say.isPending}
      />
    </div>
  );
}
