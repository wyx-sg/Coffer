# Design — knowledge-curate-and-history

## Context

Curation already runs one bounded pass per item, guarded per collection by the
upkeep-run registry and against sync by the vault-write lock. The vault-is-git
work (every vault write is a commit naming its writer, ADR
every-vault-write-is-a-validated-commit-naming-its-writer, Proposed) has not
landed: `~/.coffer/knowledge/` is plain files, and sync keeps its own working
tree that it copies in and out of.

## Decisions

### D1. The manual trigger drains a snapshot of what is pending

The route takes the collection's claim once, reads the pending list once
(inbox items oldest first, then documents edited out of band) — that list is
*m* — and runs one pass per item in that order, taking the vault-write lock per
pass rather than for the whole run, so a sync round is not held off for
minutes. An item a pass settled, or that disappeared, is skipped. It stops at
the first `failed`; `no_model` promotes the whole inbox in its one pass, so the
run ends there too. Items that arrive during the run wait for the next run or
sweep, so *m* stays what it was when the run started. `truncated` and
`too_large` do not stop the run: their items are either left owed (the sweep
puts them behind the rest) or settled, exactly as in the sweep.

The answer is `CurationRunOut {collection, status, total, passes[]}`: `status`
is `up_to_date` (nothing was pending, no pass ran), `no_model`, `failed` (the
last pass failed) or `ok`. Every pass's own `CurationOut` is in `passes`, in
order. The HTTP request stays synchronous — the answer is the list of outcomes
— and progress is read alongside it: the registry entry carries `done` and
`total`, `GET /api/v1/upkeep/runs` serves them, and after each pass a `change`
event for the collection (`kind` `knowledge`, `id` its uid) is published so a
page refetches. The CLI polls the in-flight list while it waits and prints
`curated n of m`, then one line per pass.

*Rejected:* a 202 and a background job — the spec asks for the outcomes in
the answer, and a job table is state the registry exists to avoid.

### D2. History lives in a git repository of the knowledge root, for now

`<knowledge root>/.git`, created on first use (and at boot) with a baseline
commit of whatever is already there. It is invisible to every knowledge
listing (dot-prefixed), never mirrored by sync (the tree mirror skips `.git`),
and git refuses a `.git` path from a remote. `.git/info/exclude` ignores every
dot-prefixed entry except `.inbox/`: the inbox is tracked, so a submission is a
commit and the text a pass consumed stays recoverable from history even though
the inbox file is deleted.

Every commit carries the ADR's trailers, so folding this repository into the
vault's later is a history import, not a translation:

```
Coffer-Writer: user | agent | curation | sync | disk
Coffer-Actor: <audit actor>
Coffer-Agent: <agent name>            (agent writer, or the item's author for curation)
Coffer-Operation: save | delete | submit | promote | pass | restore | undo | edit | sync
                  | create | rename | remove | baseline
Coffer-Collection: <name>
Coffer-Item: <item path>              (curation)
Coffer-Status: <pass status>          (curation)
Coffer-Restored-From / Coffer-Undoes: <commit>
```

The author name says the same thing (`Coffer (curation)`, `Coffer (user)`), and
git runs with the user's global and system config pinned to `/dev/null`, as the
sync mirror does. When git is missing, `KnowledgeHistory.available()` is false:
writes proceed unrecorded and the history routes answer 503
`KNOWLEDGE_HISTORY_UNAVAILABLE`.

*Rejected:* a repository per collection — a rename or delete would move or
drop its history, and the future vault repository is one.
*Rejected:* waiting for V1b — it changes sync's working-tree model and is its
own item.

### D3. One commit per Coffer operation; edits on disk first

A write is a transaction: under the history's lock, anything already changed in
the tree that no open transaction owns is committed first as `disk` (a
person's editor, an agent's own file tools), then the operation writes and
commits only the paths it touched. A curation pass is the long case: it opens
its transaction without holding the lock, registers each path as its tools
write it (so a concurrent save's disk snapshot leaves those alone), and commits
once at the end — `ok`, `truncated`, `too_large`, `no_model`, and even `failed`
when it had managed a write, so no write goes unrecorded. The sweep also
commits disk edits once per tick.

Sync's knowledge applier marks each path it upserts or removes; the marks are
committed as `sync` before the next disk snapshot, so another machine's change
is never mistaken for a person's edit here.

### D4. The item's agent comes from the audit log

`knowledge_written` now also records the inbox item's name. A pass looks up
that event to name the agent in `Coffer-Agent`; an item with no event (older
than this change, or migrated) falls back to its frontmatter `actor`.

### D5. Undo is exact bytes, refused on any later change

Undo is offered for `pass` commits only. For each document path the pass
touched (inbox paths excluded), any later commit touching it — after committing
disk edits — refuses the undo with `KNOWLEDGE_UNDO_CONFLICT` naming that
document and the later commit. Otherwise each document is written back to its
bytes before the pass (or removed if the pass created it), the file's mtime is
aligned to the `coffer_curated_at` stamp those bytes carry, so the sweep does
not treat the undo as a person's edit and redo the pass, and one commit
(`undo`, `Coffer-Undoes`) records it. A document the pass carried outward that
was itself an unstamped edit returns unstamped, so the sweep will offer it
again — the edit is still the person's.

Restore of one version is a person's edit: the bytes are written with a fresh
mtime and the sweep carries them outward, as for a save.

### D6. The feed reads git, the waiting items read the disk

`GET /changes` is `git log --numstat` newest first, excluding commits that
touch only inbox paths (submissions — they are the waiting items instead), and
inbox paths inside a pass are dropped from its document list. It pages by the
shared opaque cursor, keyed on the last commit id. The waiting items are the
inbox files of the collection(s) in view, each with its title, its submitter
(from the audit event, falling back to its `actor`) and its time.

### D7. The 409 carries the disk version

`KnowledgeFileConflict` gains `details` (`saved: false`, `current_body`,
`current_fingerprint`); the error handler forwards a domain error's `details`
into the envelope.

## Folding into the vault repository (V1b)

When the vault becomes one repository, `knowledge/` becomes a subtree of it:
import this repository's history under `knowledge/` (`git filter-repo
--to-subdirectory-filter knowledge` or an equivalent replay), drop
`<knowledge root>/.git`, and point `KnowledgeHistory` at the vault repository
with the same pathspecs and trailers. The routes, the writers and the undo rule
do not change.

## Risks

- A person's editor saving between Coffer's compare and its commit is
  attributed to Coffer's commit — the same window the ADR names.
- The repository grows with every edit; documents are small Markdown, so this is
  kilobytes per commit.
