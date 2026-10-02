// frontend/src/pages/sync/SyncStatusTab.tsx — Sync › Status, the landing tab.
//
// What a person opens Sync to find out, top to bottom: the one state the page
// is in (a line, or a card when it asks for something), the four area counts
// every status board shows, what waits to push, anything a stopped round or a
// join is waiting on, and every round this Mac has run.
//
// The stop and the join are fetched only while the status says there is one
// to answer; the rounds are read 30, then 50 more as the table is scrolled to
// its end, and folded in the browser over what is loaded.
import type { SyncStatus } from "@/lib/api/sync";
import { useSyncRuns } from "@/lib/hooks/useSync";
import { SyncAreaTiles } from "./SyncAreaTiles";
import { SyncJoinChoices } from "./SyncJoinChoices";
import { SyncRoundsTable } from "./SyncRoundsTable";
import { SyncStateBanner } from "./SyncStateBanner";
import { SyncStoppedCard } from "./SyncStoppedCard";
import { SyncWaitingList } from "./SyncWaitingList";
import type { SyncState } from "./syncPageState";

interface Props {
  status: SyncStatus;
  state: SyncState;
  startedAt: string | null;
  onRun: () => void;
}

export function SyncStatusTab({ status, state, startedAt, onRun }: Props) {
  // isLoading, not isPending: a disabled query stays "pending" forever.
  const rounds = useSyncRuns(true);
  const runs = rounds.items;
  const stopped = status.conflicts > 0 || status.held > 0;

  return (
    <div className="space-y-5">
      <SyncStateBanner
        status={status}
        state={state}
        runs={runs}
        startedAt={startedAt}
        onRun={onRun}
      />
      <SyncAreaTiles areas={status.areas} />
      {state.kind === "to_push" ? <SyncWaitingList waiting={status.waiting} /> : null}
      {stopped ? <SyncStoppedCard /> : null}
      {status.join_choices > 0 ? <SyncJoinChoices /> : null}
      <SyncRoundsTable
        runs={runs}
        total={rounds.total}
        hasMore={rounds.hasMore}
        isLoadingMore={rounds.isLoadingMore}
        onLoadMore={rounds.loadMore}
        isLoading={rounds.isLoading}
        error={rounds.error}
        onRetry={rounds.refetch}
        nextRoundAt={status.next_round_at}
      />
    </div>
  );
}
