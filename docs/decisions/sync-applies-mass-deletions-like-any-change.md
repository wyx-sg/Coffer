# Sync Applies a Mass Deletion Like Any Other Change; Snapshots and History Undo One Nobody Meant

**Status**: Accepted
**Date**: 2026-11-13
**Deciders**: Yuxing Wu
**Related**: [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md), [A Machine Is Identified by a Hash of Its Host's Own ID, and Owns One Descriptor in the Tree](sync-machine-identity.md), [Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](every-vault-write-is-a-validated-commit-naming-its-writer.md), [principles](../../docs-site/architecture/principles.md) (Not a second agent: what git already does, Coffer does not rebuild), research note [multi-machine sync](../research/multi-machine-sync.md), spec vault-sync "Sync a mass deletion like any other change", spec vault-sync "Snapshot before checking out and roll a round back from it", spec vault-sync "Restore to a revision without discarding later work"

## Context

A [sync round](sync-applies-clean-merges-and-stops-on-any-conflict.md)
checks a merged tree out into the vault and pushes this machine's commits with
nobody reading either. Merging against a shared base means a correct round
cannot invent a deletion. From 2026-09-22 a **deletion breaker** guarded the
rounds that might not be correct: a round was held, in either direction, when
an area would lose 20 files, or 5 files that were more than half of it, and the
person had to confirm the deletion or restore the files.

Its stated reason was a damaged vault on this machine (a reinstall that took
`~/.coffer`, a failed restore, a stray `rm -rf`) being pushed to every other
machine, or a defect in the merge turning "absent" into "deleted".

The field record never showed that case. It showed the opposite:

- The breaker's first version held the vault for a day over a re-layout that
  moved 56 documents and lost none. The uid migration held it for four days,
  28 of 28 resources "lost", with nothing wrong. Content-id pairing, uid pairing
  and a separate git rename query were added to excuse those moves.
- From 2026-10-09 to 2026-11-05 it held the owner's vault 13 times, 28 to 136
  files each. Every one was Coffer's own work (the memory sync, a Tidy the owner
  started). Every answer was "delete". A second rule was added to set aside
  deletions whose commit Coffer could explain, and a third to remember an
  answer by file, because the same hold was asked twice.
- The owner asked on 2026-11-13 for the logic to be removed: it is not needed.

The breaker grew three exception mechanisms, a stop kind, three HTTP routes,
three CLI commands, two review pages and a desktop alert, all to ask a question
whose answer was always yes. Meanwhile every round already tags a pre-apply
snapshot before checking out, a round can be rolled back from it, and every
deleted file stays in the vault's git history on every machine.

## Options Considered

### Option A — Remove the breaker; a deletion syncs like any other change (chosen)

A round applies and pushes a deletion however many files it removes, in either
direction. A deletion nobody meant is undone the way any unwanted change is:
roll back, from its snapshot, the round that pulled it on another machine, or
restore a revision from the vault's history on any machine. The rollback is a new
commit, so the next round publishes the restore to every machine.

Pros: nothing waits on the person for a question that is always answered yes;
the stop on conflict becomes the round's only stop, so one stop kind, one
banner, one Overview item; about three thousand lines of code, tests and pages
go, along with the pairing heuristics whose only purpose was to keep the
breaker quiet. It matches what git, Syncthing, Obsidian Sync, Dropbox and the iCloud and Google
drives do.

Cons: a wiped vault pushed by mistake reaches the other machines before anyone
notices, and is undone after the fact rather than prevented. Accepted: the
other machines each snapshot before they check it out, the history keeps every
file, and a wipe produces a round whose record shows the removed files, so it
is seen and reversed with one rollback.

### Option B — Keep the breaker as it is

Pros: a wiped disk is stopped before it is published.

Cons: the field record above. In two months it fired only on Coffer's own
operations, and a prompt that is always answered the same way trains the
person to click through the one that would matter (the reason the breaker's
own ADR rejected "confirm every deletion").

Lost on the owner's decision and the field record.

### Option C — Make it configurable (off by default, or tunable thresholds)

Pros: whoever wants the guard keeps it.

Cons: all the code, the pages and the exception rules stay, for a setting
nobody turns on. A tunable threshold is one a frustrated person raises to
100% the first time it holds them. The owner asked for removal, not a switch.

Lost: a switch is the over-design the lean principle removes.

### Option D — Warn, do not block (like Dropbox)

Apply the round, then raise an Overview item listing the mass deletion with a
rollback button.

Pros: the person learns of a large deletion without waiting on it.

Cons: still needs the thresholds and the pairing rules to decide what is
"large", so it keeps most of the code; and the warning would fire on the same
memory-sync and Tidy runs, so it would be ignored the same way. The round's
record already lists what it removed, and the Sync page already offers the
rollback.

Lost: the existing round record and rollback cover it without a new rule.

### Option E — Tombstones or a deletion log

Apply only deletions recorded as explicit tombstones.

Pros: a deletion is an assertion, not an inference.

Cons: git history already records each deletion against a shared base, and a
wiped vault would write tombstones for everything it lost. The first sync
design used them and they did not prevent the 2026-07-10 mutual deletion.

Lost: redundant with git and blind to the case it would be for.

## Comparable products

From the research note [multi-machine sync](../research/multi-machine-sync.md)
("Mass-deletion protection in consumer sync") and the products' own docs:

- **git** itself pulls and pushes deletions of any size; recovery is the
  history (`git checkout <rev> -- path`, `git revert`).
- **Syncthing** has no deletion count. Its one guard is the `.stfolder`
  marker: a folder whose marker is missing (an unmounted disk) is not synced at
  all. Deleted files are recovered from per-folder versioning.
- **Obsidian Sync** applies deletions as they happen and keeps version history
  and a deleted-files view to restore from.
- **Dropbox** applies the deletion, then emails a summary after a large one,
  with a restore link; deleted files are recoverable for 30 days or more.
- **iCloud Drive** and **Google Drive** apply deletions and keep a "Recently
  Deleted" / Trash for 30 days.
- **OneDrive** is the one that holds: deleting more than 200 files in a short
  time asks whether to remove the cloud copies, and an administrator can make
  an unanswered prompt keep the files for seven days. It is a policy for
  people deleting by hand in a file manager, where an accidental drag is
  common.

Most of them rely on recovery after the fact, which Coffer's snapshots and
history already give. OneDrive's prompt is the breaker this ADR removes; in
Coffer the large deletions come from Coffer's own operations, not a person's
mis-drag, so the prompt protected nothing. Syncthing's marker answers a
different failure (a missing folder), which Coffer's vault, a git repository
checked at step 0 of every round, already refuses.

## Decision

Option A. A sync round applies and pushes a deletion of any size in either
direction, and holds nothing for confirmation. The pre-apply snapshot, rollback
and the vault's history are the recovery. The breaker, its pairing rules, the
hold routes and commands, the deletion review page and the
`awaiting_confirmation` alert are deleted. History rows an earlier build
recorded as `held` still read, and a hold an earlier build left in
`local/sync/round.json` is dropped when it is read.

## Consequences

- A conflict is the only reason a round stops for the person. The Overview
  shows at most one sync item per situation, and the sync health tile counts
  items that need attention, not "held" rounds.
- A layout or identity migration Coffer ships publishes without any pairing
  logic; a move is simply a deletion plus an addition in one commit.
- A wiped vault is undone by rolling back the round that pulled it on any
  machine that has the files; the next round pushes the restore.
- Reintroducing a guard later would mean a new decision here, argued against
  this field record.
