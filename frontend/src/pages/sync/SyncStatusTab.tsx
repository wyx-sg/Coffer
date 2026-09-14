// frontend/src/pages/sync/SyncStatusTab.tsx — Sync → Status.
//
// The order on this tab is the point. Two states have to be read before
// anything else, so they are banners at the top rather than lines inside the
// round report:
//
//   Conflict  — the round stopped, the vault is untouched, and the user has to
//               reach for their own git in the working tree.
//   Pending   — the deletion guard held a round and is waiting for an answer
//               that can destroy data in either direction.
//
// Below them sit the remote's configuration + "converge now", and the master
// key — which is on THIS page and not in Settings because its whole purpose is
// making another machine able to decrypt what this one syncs.
//
// What the last round DID is not here any more. One round rendered as prose
// could say what just happened but never what has been happening, and every
// question a user brings to this page past the first — has it been running,
// when did it stop, which round published those 300 documents — is a question
// about the sequence. That is the History tab. The last round is still read
// here, but only for the two things that are a state rather than a record: a
// conflict the user has to resolve, and a round held at the deletion guard.
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import { useSyncStatus } from "@/lib/hooks/useSync";
import { SyncConflictBanner } from "./SyncConflictBanner";
import { SyncMasterKeyCard } from "./SyncMasterKeyCard";
import { SyncPendingBanner } from "./SyncPendingBanner";
import { SyncRemoteCard } from "./SyncRemoteCard";

export function SyncStatusTab() {
  const { t } = useTranslation();
  const { data, isPending } = useSyncStatus();

  if (isPending) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-muted-foreground">
          {t("common.loading")}
        </CardContent>
      </Card>
    );
  }

  const round = data?.last_run ?? null;
  const worktree = data?.remote?.worktree_path ?? null;

  return (
    <div className="space-y-6">
      {round && round.conflicts.length > 0 ? (
        <SyncConflictBanner paths={round.conflicts} worktree={worktree} />
      ) : null}
      {round?.pending ? <SyncPendingBanner pending={round.pending} /> : null}

      <SyncRemoteCard status={data ?? null} />
      <SyncMasterKeyCard />
    </div>
  );
}
