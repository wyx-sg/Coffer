// frontend/src/components/workflow/WorkflowStatusBadge.tsx
// The status vocabulary for a run and for a node, in one file so the two can
// never drift apart. Colour comes from `lib/statusColors.ts` (the status.*
// tokens), never from a palette class picked here.
//
// A run has six statuses and a node seven, and they are deliberately different
// sets: "waiting for the developer" is a property of a NODE, never of a run,
// so no run ever renders a waiting badge.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { toneClass, type Tone } from "@/lib/statusColors";
import type { NodeStatus, RunStatus } from "@/lib/api/workflow";

const RUN_TONE: Record<RunStatus, Tone> = {
  draft: "muted",
  running: "ok",
  paused: "warn",
  completed: "ok",
  aborted: "muted",
  failed: "error",
};

const NODE_TONE: Record<NodeStatus, Tone> = {
  pending: "muted",
  running: "ok",
  // Both waits are the run asking the developer for something, which is a
  // caution (the run is stopped), not a fault.
  waiting_review: "warn",
  waiting_approval: "warn",
  completed: "ok",
  skipped: "muted",
  failed: "error",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  const { t } = useTranslation();
  return (
    <Badge variant="secondary" className={toneClass(RUN_TONE[status])}>
      {t(`workflow.runStatus.${status}`)}
    </Badge>
  );
}

export function NodeStatusBadge({ status }: { status: NodeStatus }) {
  const { t } = useTranslation();
  return (
    <Badge variant="secondary" className={toneClass(NODE_TONE[status])}>
      {t(`workflow.nodeStatus.${status}`)}
    </Badge>
  );
}
