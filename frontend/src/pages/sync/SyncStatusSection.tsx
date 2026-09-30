// frontend/src/pages/sync/SyncStatusSection.tsx
//
// Everything above the Runs table, in the order a person needs it: is sync
// working, what is wrong, what a stopped round or a join is waiting on, and
// what is waiting to push.
//
// Each card renders only while its situation holds, gated on the status the
// page already polls — so the stop and the join are fetched only when the
// status says there is one to answer.
import { useSyncStatus } from "@/lib/hooks/useSync";
import { useSyncStop } from "@/lib/hooks/useSyncStop";
import { SyncConflictCard } from "./SyncConflictCard";
import { SyncHoldCard } from "./SyncHoldCard";
import { SyncJoinCard } from "./SyncJoinCard";
import { SyncJoinChoices } from "./SyncJoinChoices";
import { SyncStatusCard } from "./SyncStatusCard";
import { SyncWaitingList } from "./SyncWaitingList";

function StoppedRound() {
  const { data } = useSyncStop(true);
  const round = data?.stopped ? data.round : null;
  if (!round) return null;
  if (round.kind === "hold" && round.hold) return <SyncHoldCard hold={round.hold} />;
  return <SyncConflictCard round={round} />;
}

export function SyncStatusSection() {
  const { data: status } = useSyncStatus();
  if (!status) return null;
  const stopped = status.conflicts > 0 || status.held > 0;

  return (
    <div className="space-y-4">
      <SyncStatusCard status={status} />
      {stopped ? <StoppedRound /> : null}
      {status.configured && !status.joined ? <SyncJoinCard /> : null}
      {status.join_choices > 0 ? <SyncJoinChoices /> : null}
      <SyncWaitingList waiting={status.waiting} />
    </div>
  );
}
