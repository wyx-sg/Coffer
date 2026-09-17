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
// SEND BACK is in the header and is not an exception to any of that, because
// it does nothing to this task: it opens a NEW task in an earlier stage
// (FR-025), the way "Add task" does on the map. It is a button rather than a
// sentence because which edge is crossed and how often it may be crossed are
// the template's to answer, and this task's agent cannot answer them.
//
// The page is a WORKSPACE rather than a document — full-bleed, one screen
// tall, the conversation taking every pixel the header does not — because a
// transcript that a run spent hours writing is the content, not an attachment
// to a status header.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { CornerUpLeft, MessageSquareDashed, Workflow } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { NodeThread } from "@/components/workflow/NodeThread";
import { SendBackDialog } from "@/components/workflow/SendBackDialog";
import { NodeStatusBadge } from "@/components/workflow/WorkflowStatusBadge";
import { translateApiError } from "@/lib/api/errors";
import { useWorkflowRun } from "@/lib/hooks/useWorkflowRun";
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
const GUTTER = "shrink-0 px-6 pt-10 md:px-10";

/** Run statuses that refuse every command, send-back included (FR-013). */
const TERMINAL = ["completed", "aborted", "failed"];

export function WorkflowNodePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { runId = "", nodeKey = "" } = useParams<{ runId: string; nodeKey: string }>();
  const { data: detail, isPending, error } = useWorkflowRun(runId);
  const [sendingBack, setSendingBack] = useState(false);

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
  // Only the edges leaving THIS stage, and only while this machine may still
  // command the run: a send-back is a command like any other (FR-012, FR-013).
  const edges = (detail.send_backs ?? []).filter((edge) => edge.from_stage === stage.key);
  const canSendBack = edges.length > 0 && run.owned_here && !TERMINAL.includes(run.status);

  return (
    <div className={WORKSPACE}>
      <div className={GUTTER}>
        <PageHeader
          back={back}
          title={node.name}
          subtitle={t("workflow.nodeConversation.subtitle", {
            run: run.title,
            stage: stage.name,
            type: t(`workflow.node.types.${node.type}`),
          })}
          actions={
            canSendBack ? (
              <Button variant="outline" size="sm" onClick={() => setSendingBack(true)}>
                <CornerUpLeft aria-hidden />
                {t("workflow.sendBack.action")}
              </Button>
            ) : undefined
          }
          badges={
            <div className="flex flex-wrap items-center gap-2">
              <NodeStatusBadge status={node.status} />
              <Badge variant="outline">{t("workflow.node.attempt", { count: node.attempt })}</Badge>
              {node.adhoc ? (
                <Badge variant="secondary">{t("workflow.node.unplanned")}</Badge>
              ) : null}
              {node.skill ? <Badge variant="outline">{node.skill}</Badge> : null}
            </div>
          }
        />

        {latest?.failure_reason ? (
          <p className="pt-2 text-sm text-destructive">
            {t(`workflow.node.failure.${latest.failure_reason}`)}
          </p>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 px-6 pb-6 pt-4 md:px-10">
        {latest?.conversation_id ? (
          <NodeThread
            conversationId={latest.conversation_id}
            ownedHere={run.owned_here}
            runId={run.id}
            attemptId={latest.id}
          />
        ) : (
          // Honest rather than empty: a task that never started has no
          // transcript, and an empty thread would read as one that said nothing.
          <EmptyState
            icon={MessageSquareDashed}
            title={t("workflow.nodeConversation.notStartedTitle")}
            description={t("workflow.nodeConversation.notStartedBody")}
          />
        )}
      </div>

      <SendBackDialog
        runId={run.id}
        version={run.version}
        edges={edges}
        open={sendingBack}
        onClose={() => setSendingBack(false)}
        onSent={(key) => navigate(`/runs/${run.id}/nodes/${encodeURIComponent(key)}`)}
      />
    </div>
  );
}
