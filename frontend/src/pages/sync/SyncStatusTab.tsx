// frontend/src/pages/sync/SyncStatusTab.tsx — Sync › Status, the landing tab.
//
// What a person opens Sync to find out, top to bottom: the one state the page
// is in (a line with the areas line under it, or a card when it asks for
// something), what a join is waiting on, and every round this Mac has run.
// No file is listed here: changes to push, held deletions and conflicts each
// open their own review page from the banner (SyncReviewShell).
//
// The stop and the join are fetched only while the status says there is one
// to answer; the rounds are read 30, then 50 more as the table is scrolled to
// its end, and folded in the browser over what is loaded.
import type { SyncStatus } from "@/lib/api/sync";
import { useSyncRuns } from "@/lib/hooks/useSync";
import { SyncJoinChoices } from "./SyncJoinChoices";
import { SyncRoundsTable } from "./SyncRoundsTable";
import { SyncStateBanner } from "./SyncStateBanner";
import type { SyncState } from "./syncPageState";

interface Props {
  status: SyncStatus;
  state: SyncState;
  startedAt: string | null;
  onRecheck: () => void;
  rechecking: boolean;
}

export function SyncStatusTab({ status, state, startedAt, onRecheck, rechecking }: Props) {
  // isLoading, not isPending: a disabled query stays "pending" forever.
  const rounds = useSyncRuns(true);
  const runs = rounds.items;

  return (
    <div className="space-y-5">
      <SyncStateBanner
        status={status}
        state={state}
        runs={runs}
        startedAt={startedAt}
        onRecheck={onRecheck}
        rechecking={rechecking}
      />
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
