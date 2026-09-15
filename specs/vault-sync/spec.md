# Spec — Vault Sync

> 中文版: [spec.zh.md](./spec.zh.md)

Keep one vault across the user's own machines by converging each of them with a
git repository the user owns. A background worker commits what this vault
holds, lets git three-way-merge it against what the remote holds, and applies
the resulting difference back — deletions included. Background and alternatives
in [Vault Sync](../../docs/decisions/vault-sync.md).

## Why

A developer works the same project from a laptop and a desktop. Both produce
vault state: knowledge files, skills, MCP registrations, agent configuration,
credentials. Without convergence each machine is an island, and the fix — export
here, carry the directory, import there — is a chore nobody performs often
enough for the two to stay alike.

Convergence with a user-owned git remote is a bounded exception to the
constitution's local-first principle (0.6.0): the remote is a **rendezvous, not
a system of record**. Every machine's vault stays complete and authoritative, so
the remote can be deleted and rebuilt from any single machine without losing
anything.

## What syncs

- **Knowledge** — the markdown files under `~/.coffer/knowledge/<collection>/`.
- **Skills** — the master skill store under `~/.coffer/skills/`.

  Both trees are mirrored as regular files. A symlink is skipped, not followed
  — its target is not vault content, and a link to a file outside the vault
  would otherwise be published — and anything under a nested `.git` directory
  is skipped as another repository's internals. What was skipped is logged
  once per round. In the other direction, a symlink the working tree holds is
  refused rather than read into the vault.
- **Config resources** — `mcp_server`, `agent`, `skill`, `knowledge`, `memory`,
  `provider` definitions (system of record is SQLite; serialized to text). A
  resource document is identity, description and config — what the resource
  *is*. What it reaches is not in it; see below.
- **Shared state** — module-owned areas that belong to the vault rather than to
  one machine: MCP capability preferences, internal engine settings, and the
  agent plugin inventory.

  Channel peer pairings were such an area and no longer are. The argument for
  them was that pairings are platform-level, so rebinding a channel to another
  machine would need no re-pairing — and a channel does not reach another
  machine any more, so there is no rebinding left for them to save. Every
  published document would name a channel the other side does not have.

  The plugin inventory is an **inventory, not a replicator**: it records which
  plugins each agent has on each machine and writes nothing into any agent's
  configuration.
- **Credentials** — Fernet **ciphertext only**, and only when the user opts in.
- **Machine descriptors** — one small document per machine, described below.

## What does not sync (machine-local)

Logs, `coffer.db` itself, `daemon-config.json`, PID files, port allocations,
chat history, conversations, the audit log, MCP invocation records, and any
runtime artifact. The master key is **never** written into the repository.

Two entries in this list are decisions rather than mechanics, and both say the
same thing: what a machine *does* with the vault belongs to that machine.

- **Reach** — a resource's `enabled` flag and its `scope`. They read like two
  fields but they are one thing, written by one control: whether this resource
  is live here, and for which agents. Reach is set on the machine it applies to
  and each machine sets its own. Publishing it would let one machine silently
  re-answer a question another machine had already answered for itself — the
  laptop that deliberately left a server dark would find it live again after the
  desktop's next round, with nothing in the history that reads like a decision
  anyone made.
- **Channels** — the `channel` kind is not exported at all. A channel is an
  inbound surface bound to one machine: its port, its tunnel, the webhook URL a
  platform has been told to call. A channel arriving on a second machine is at
  best inert and at worst a second machine answering the same conversation, so
  there is nothing for it to be worth.

A round MUST ignore `resources/channel/**` in **both** directions, and the
inbound half is a safety property rather than tidiness. A machine that stops
exporting channel documents publishes the removal of the ones already in the
tree as an ordinary deletion; a machine that honoured that deletion would lose
the channels it configured for itself. So the tree tidies itself once, and no
vault is touched by it. Publishing that one-time batch of deletions may trip the
deletion guard on a small vault, which is correct — the user is shown exactly
which paths are going and confirms once.

Conversations and the audit log are deliberately excluded: they are records of
what happened *on a machine*, and a merged history of two machines' activity
would be a different feature with a different shape (see `/activity`).

## Concepts

- **Sync remote** — at most one git repository, owned by the user, that this
  vault converges with. Configured with a URL, a branch, a push credential
  reference, an interval, and whether credential ciphertext rides along.
  Disabled until the user configures it. The URL and the branch become
  arguments to `git`, so neither may begin with `-` (git would read it as an
  option, and `--receive-pack=<cmd>` is a command), and the branch is held to
  `git check-ref-format --branch`. Both are refused at the API and CLI and
  again by the domain object; the adapter fences every positional argument
  git lets it fence with `--` and pushes an explicit `refs/heads/` refspec.
- **Working tree** — the directory the vault is serialized into, which is also
  the git working tree. Default `~/.coffer/sync`. Every round mirrors the vault
  *into* it and may `reset --hard` it, so it may not be at, inside or above
  any vault directory (knowledge, skills, memory), nor at or above `~/.coffer`
  itself; inside `~/.coffer` only the default location is accepted, and a
  relative path is refused. An existing repository there is adopted with its
  history intact — unless it has commits and an `origin` that is not the
  configured remote and was not created by Coffer, in which case it is
  someone's checkout of something else and is refused rather than repointed.
  A tree Coffer made is marked in its local git config and can be repointed
  when the remote's URL changes.
- **Vault document** — the serialized form of one piece of vault state at one
  path in the working tree: a knowledge file, a skill file, a resource YAML, a
  state YAML, a credential blob, a machine descriptor.
- **Converge round** — one full cycle: serialize local state, merge with the
  remote, apply what the merge brought in, push. Specified below.
- **Pointer** — the commit this vault has provably absorbed, stored locally.
  It is the base of every diff and the only machine identity the algorithm
  needs. It never travels.
- **Retry set** — paths the working tree holds that this vault has not absorbed.
  Stored locally beside the pointer. The exporter must not delete them.
- **Machine** — one installation of Coffer, identified by a stable id derived
  from the host, carrying a display name the user may change freely.

## The machine dimension

### Identity is derived, the name is a label

A machine has two separate things:

| | `machine_id` | `machine_name` |
| --- | --- | --- |
| Origin | derived from the host OS | chosen by the user, defaults from hostname |
| Is it a key? | **yes** — descriptor filename, tidy-owner reference, table key | no |
| Mutable? | no | **yes, at any time, at no cost** |
| Stored | cached in `daemon-config.json`, recomputed if lost | inside the machine's descriptor, so it syncs |

`machine_id` MUST survive reinstalling and uninstalling Coffer, because a
machine that comes back under a new identity becomes a ghost: it rejoins as a
stranger rather than as itself, its old descriptor lingers in the registry with
nobody to update it, and anything that named it — the tidy owner, its own
recovered pointer — silently stops meaning this machine. It is therefore derived
from the host, not generated by Coffer:

- **macOS** — `IOPlatformUUID` from `IOPlatformExpertDevice`.
- **Linux** — `/etc/machine-id`, falling back to `/var/lib/dbus/machine-id`.
- **Fallback** — when neither is readable, a UUID generated once and stored at
  `~/.coffer/machine-id` (mode `0600`). This one does **not** survive deleting
  `~/.coffer`, and the machine page says so, because such a machine reappears
  under a new id and the old descriptor must be removed by hand.

The raw host identifier MUST NOT be written into the repository — it is a
hardware identifier. What travels is `sha256("coffer-machine:" + raw)`
truncated to 16 hex characters.

### The registry is a derived view, not a synced table

Each machine writes exactly one document, at `machines/<machine_id>.yaml`, and
**writes no other machine's**. Because every machine owns a disjoint path, these
documents cannot conflict; git merges them trivially. The registry is whatever
`machines/*.yaml` currently holds.

A descriptor carries: `name`, `os`, `hostname`, `coffer_version`,
`last_converged_at`, `last_converged_commit`, `key_fingerprint`, and the names
of the agents registered on that machine.

`last_converged_commit` is this machine's pointer, published so the remote can
hand it back. The pointer itself is local state and may be lost — to a
reinstall, a wiped `~/.coffer`, a restored-from-elsewhere disk — and a machine
that rejoins without it is the dangerous case the next section handles.

`key_fingerprint` is the same short hash `GET /sync/key/fingerprint` returns, so
the machines table can state directly that another machine's credentials cannot
be decrypted here, instead of the user comparing fingerprints by hand.

`last_converged_at` is restamped **at most once per calendar day**, so a machine
that is running but idle does not commit a heartbeat every round. It therefore
means "last day this machine converged", and the UI says so.

### Scope has no machine axis, because reach does not travel

`scope` names agents and nothing else:

```yaml
scope:
  agents: [claude-code]
```

`null` means every agent, a list restricts to it, and `[]` matches nothing —
dormant. An unknown agent name is legal and simply never matches.

There is no machine axis and there is nothing for one to say. Reach is
machine-local (`## What does not sync`), so a machine already names the
resources it activates by *holding* that scope; machine ids inside the scope
would record the same fact a second time, in a second place, with two ways to
disagree. "Live on the desktop, dark on the laptop" is expressed by setting it
that way on each — which is also the only expression the user can verify from
the machine they are sitting at.

Removing the axis MUST NOT widen anything. A stored scope that named machines
was, on this machine, either admitted by that list or dormant because of it; the
migration resolves each row against the machine id the daemon was actually using
and writes the answer that machine already saw, taking `agents: []` — dormant —
whenever it cannot tell. Narrowing is visible and one click to undo; widening is
a resource silently reaching an agent it was kept from.

A scope editor MUST state, where the user sets reach, that reach applies to this
machine only and is not synced. Where a resource is dormant here, it MUST say so.

## The converge round

A round is seven steps, and the order is the specification's most important
content: it is what prevents the mutual deletion of 2026-07-10.

```
0  Repair    — if the working tree's HEAD is not the pointer, reset to the pointer
1  Serialize — export the vault into the tree (differentially), commit as L
2  Merge     — fetch, then merge origin/<branch> into L with base merge-base(L, R) → M
3  Diff      — D := git diff L..M
4  Guard     — circuit-breaker check on D; tag L as the pre-apply snapshot
5  Apply     — apply D to the vault, path by path
6  Publish   — push M; pointer := M; unapplied paths join the retry set
```

### Why local state is committed before the merge

Pulling first and then applying would lose local edits. With the tree at the
pointer and no local commit, a fetch fast-forwards, git is never given the
chance to three-way-merge, and applying the remote's changes overwrites whatever
the vault changed on the same path.

Committing local state first gives git the three inputs it needs — base `P`,
local `L`, remote `R` — so different hunks of one file merge, the same hunk
conflicts, and the diff `L..M` contains **exactly what the remote contributed**.
The vault equals `L` at that moment, so applying `L..M` lands it on `M` with
local edits intact.

### Why deletion is safe

Deletion is only ever applied when it appears in `D` as a deletion, and a
deletion can only reach `D` because some machine actually deleted that document
relative to a shared base. A machine that merely *lacks* a document makes no
change relative to its own base, and git treats "unchanged" as an assertion
about nothing.

This is the guarantee the 0.3.0 design could not make, because its export
rewrote the tree from local state wholesale — which made "I never had it" and
"I deleted it" indistinguishable in the diff git saw.

Two rules preserve the honesty of that diff, and both are normative:

- **Export writes differentially.** It writes changed documents and removes
  documents the vault no longer holds. It MUST NOT clear and rewrite a
  directory.
- **Export never deletes a path in the retry set.** A document this vault failed
  to absorb is pending, not deleted.

### The pointer advances only on absorption

The pointer may advance to `M` when the round completes. Any path whose
application failed joins the retry set instead, is re-attempted next round, and
leaves the set on success. A path that fails because it cannot apply on this
machine at all — an `agent` whose `config_dir` does not exist here — is recorded
as **not applicable here** rather than pending: it is preserved like a retry-set
path, but it is not retried and not reported as an error, and the UI says so
rather than presenting it as a failure the user has to chase.

### Joining a remote

A machine with no pointer is joining. There are two kinds of joiner and they
need opposite treatment, so the round MUST tell them apart before it does
anything. It can: the remote's registry either holds this machine's id or it
does not, which is what a **derived** machine id buys.

**A new machine takes the union.** Its id is absent from the registry. The
pointer is set to git's empty tree, so `D` is a diff from nothing and can only
contain additions. The machine takes everything the remote holds, keeps
everything it already had, and the next round publishes both. Deletion is
structurally impossible here, not merely avoided.

**A returning machine recovers its base.** Its id is present, so it has
converged before and its descriptor names the commit it reached. That commit
becomes the pointer, and the round proceeds as an ordinary stale-machine
round: the three-way merge takes the remote's deletions, keeps this machine's
edits, and nothing resurrects.

Treating a returning machine as new is the failure this rule exists to prevent.
Its vault still holds what it held before it lost its pointer, so a union
republishes state the other machines deleted while it was away — every deletion
undone at once, and no conflict raised, because a union has no base to disagree
with.

**A returning machine whose vault is gone must not publish the loss.** The
recovered base is only correct if the vault still holds roughly what that commit
held. A reinstall that took `~/.coffer` with it leaves an empty vault and a valid
pointer, and the merge would read that as "this machine deleted everything" —
the 2026-07-10 shape, reached from the other direction. Coffer cannot tell a
wiped disk from a deliberate purge, so it does not try: the publish-side
circuit breaker below stops the round and asks.

Joining is therefore an explicit, reported act. Whichever kind it is, the surfaces
state what was found before anything is applied — which case it is, when this
machine last converged, how many documents the remote has changed since, and how
many this vault has.

**A damaged machine gets a third answer.** Where the publish-side guard holds a
round, confirm and reject are both wrong for a vault that lost its files:
confirming spreads the loss to every other machine, rejecting refuses the same
round forever. **Rebuild** replaces this vault with the remote's, discarding
documents only this machine holds and pushing nothing. It is destructive on
purpose and is never reached without the user asking for it by name.

A returning machine whose recorded base is no longer in the remote's history has
no safe default either — joining as new would resurrect what the others deleted,
rebuilding would discard what only this one has — so that case is refused until
the user picks one.

The same detection runs whenever a round starts with no pointer, not only under
`coffer sync adopt`, so configuring a remote on a machine that has forgotten its
pointer cannot skip it.

## Applying a diff

| Path | Added / Modified | Deleted |
| --- | --- | --- |
| `knowledge/**`, `skills/**` | write the file | remove the file |
| `resources/<kind>/<name>.yaml` | upsert through the resource service, with `${HOME}` expanded and the kind's import gate run; the local resource's reach is **not** touched | delete the resource |
| `resources/channel/**` | nothing, in either direction | nothing |
| `state/<area>/**` | the area's provider applies the document | the area's provider removes it |
| `credentials/<ref>.enc` | write the ciphertext, subject to the freshness rule below | delete the credential |
| `machines/*.yaml` | nothing — the registry is read from the tree | nothing |
| `manifest.json` | ignored | ignored |

Deleting a resource releases the credentials no remaining resource cites, as any
other deletion does. After the diff is applied, each kind's post-import hook
re-applies its machine-local side effects — native config projections, shims,
skill deliveries — from current state.

A state document reaches the tree only while there is a decision to carry, so
its deletion is that decision being taken back, and each area honours it in its
own terms:

- **`state/memory-overrides/<digest>`** — the override whose fact key digests to
  the document's name is cleared.
- **`state/mcp-preferences/<server>`** — a document exists only while something
  on that server is disabled, so its deletion re-enables every capability on
  that server. The preference rows stay: enabled is their default, and their
  seen-timestamps are this machine's own. A server not registered here is
  ignored.
- **`state/settings/internal-engine`** — the singleton is reset to its defaults
  (no model, tidy off, no tidy owner). The defaults publish **no** document —
  neither a machine that never chose nor one whose choice was taken back writes
  one — which is what stops a fresh machine, which never persists a default it
  already has, from deleting the document again every round.
- **`state/agent-plugins/<agent>`** — nothing is dropped locally: the inventory
  has no local store beyond the document itself, and Coffer has no
  uninstall-by-sync path any more than it has an install one. What this
  machine's agent holds is a fact about this machine, and the next export
  republishes it if it is still there.

Per-path failures are reported and never abort the round.

## Conflicts

Most concurrent edits are not conflicts: git merges different hunks of one file
without help. What follows governs the remainder.

1. **Credential blobs never reach a text merge.** A Fernet token carries its
   encryption time in cleartext, so two ciphertexts for one ref can be ordered
   without the key. The fresher encryption wins. This rule applies to
   `credentials/*.enc` and to nothing else.
2. **An agent may attempt the rest.** When an internal model is configured, a
   bounded pass resolves the remaining conflicts **in the working tree only**,
   never against the live vault. Its output MUST pass a validation gate — the
   document parses, a resource document validates, and no conflict marker
   remains — before it is treated as an ordinary merge result. Resolutions are
   always reported with their paths, whether or not they succeeded, because a
   silent machine merge of the user's own notes is precisely what the user would
   want to know about.
3. **Otherwise the round stops.** With no model configured, or when the pass
   fails or its output fails the gate, the round aborts: the vault is not
   touched, the pointer does not move, and the surfaces name the conflicted
   paths and the working tree that holds them. The user resolves with their own
   git tools and the next round proceeds.

A conflict blocks convergence on both machines until it is resolved. That is
intended: two machines quietly disagreeing about one document is worse than two
machines waiting.

## Safety

Bidirectional convergence writes the vault without a human in the loop, so two
guards are normative.

- **Pre-apply snapshot.** Step 4 tags `L`, whose tree is by construction the
  vault's state immediately before the apply. Rollback is the same machinery run
  backwards — apply `M..L`. The most recent ten snapshots are kept.
- **Circuit breaker, in both directions.** A round whose diff would delete more
  than 20% of the documents in an area, or 20 or more documents in one area,
  does not proceed. The two thresholds are fixed, not configured. It is
  recorded as needing confirmation, the surfaces list what it would remove, and
  the user accepts or rejects it. On the apply side the guard runs over
  everything the round is about to apply — the incoming diff **and** the retry
  set, since a held path the tree has since dropped is absorbed as a deletion.

  The guard applies to what the round would **apply to the vault** and, equally,
  to what the round's own export would **publish as a deletion**. The second
  direction is the one that matters when this machine is the damaged one: a
  vault that lost its files to a reinstall, a failed restore or a stray
  `rm -rf` would otherwise publish that loss as an ordinary deletion and take
  the other machines down with it. A machine joining as new has no deletions in
  either direction and is unaffected.

Neither guard replaces the diff-based apply; they bound the damage of a defect
in it.

## Unattended rewriters

A worker that rewrites vault content with no human approving the diff is safe on
one machine and unsafe on several. The knowledge **tidy** pass is the case that
exists today: it merges duplicate notes, splits overgrown ones, and deletes the
file whose content now lives elsewhere.

Run on two machines over one corpus, it produces a failure git cannot see. Each
machine merges notes `n1` and `n2` into a topic document, but into *different*
documents — `t1` here, `t2` there. The merge is clean: both machines agree `n1`
and `n2` are deleted, and `t1` and `t2` are additions at different paths. The
vault ends up holding the same knowledge twice, and nothing was in conflict.

Three rules follow, and they are normative.

- **An unattended rewriter of synced content names one owner machine.** The tidy
  setting gains an owner, becomes synced state, and a pass is a no-op on every
  other machine. Tidy is off by default and installation-wide already, so this
  costs a field rather than a concept. If the owner machine is off, no tidy
  happens, which is the correct trade for a background nicety.
- **A pass and a converge round never overlap.** They both write the vault, and
  an export taken mid-rewrite is a torn snapshot. They take the same lock. A
  pass is also skipped while a conflict or a pending confirmation is
  outstanding, so rewrites are never piled onto an unresolved divergence.
- **Delete-versus-edit resolves toward the edit.** When the owner's pass deleted
  a document that another machine edited, the edit is kept and the deletion is
  dropped. A fresh edit is something a person or an agent just decided; the
  deletion is a housekeeping judgement the next pass will simply make again.

The retention worker needs none of this: it prunes the audit log, MCP invocation
records and conversations, none of which sync.

## Determinism and path portability

Resource and state serialization MUST be deterministic — sorted keys, normalized
timestamps, machine-local fields stripped — so that an unchanged vault produces
an unchanged tree. Determinism is what makes a round with nothing to say produce
no commit, and what makes the history readable with the user's own git tools.

Absolute paths under `$HOME` are stored against a `${HOME}` sentinel and
expanded against each machine's home — in resource documents and in state
documents alike. Paths outside `$HOME` are stored verbatim and may fail to
apply on another machine, which surfaces as a per-path failure.

## Credentials

Credential ciphertext travels only when the remote is configured to carry it.
The master key is never written into the repository; it is bootstrapped onto
another machine out-of-band with `coffer sync key export` / `coffer sync key
import`, and a machine holding ciphertext without the key reports those refs
locked rather than failing decryption silently.

The push credential is resolved from the credential store at push time, named by
reference and never by value. It never enters the repository's git config, never
appears in a command line, and is redacted from any recorded error.

## Restore

The remote's history is also the vault's backup. `coffer sync restore [--at
<rev|date>]` moves the working tree to a revision and applies the difference
from the current pointer, so a document deleted last week returns without
discarding anything the vault gained since. Restore is always explicit; a round
never reaches back into history on its own.

## Surfaces

| Surface | Operation |
| --- | --- |
| CLI | `coffer sync rebuild` · `coffer sync remote set <url> [--branch] [--interval] [--with-credentials] [--credential-ref]` · `coffer sync remote show` · `coffer sync remote clear` · `coffer sync adopt <url>` · `coffer sync now` · `coffer sync status` · `coffer sync restore [--at <rev\|date>]` · `coffer sync confirm` · `coffer sync reject` · `coffer sync rollback` |
| CLI (machines) | `coffer sync machines` · `coffer sync machine rename <name>` · `coffer sync machine remove <id>` |
| CLI (key) | `coffer sync key export <file>` · `coffer sync key import <file>` |
| HTTP | `GET\|PUT\|DELETE /api/v1/sync/remote` · `POST /api/v1/sync/run` · `POST /api/v1/sync/adopt` · `GET /api/v1/sync/status` · `GET /api/v1/sync/runs` · `POST /api/v1/sync/restore` · `POST /api/v1/sync/confirm` · `POST /api/v1/sync/reject` · `POST /api/v1/sync/rebuild` · `POST /api/v1/sync/rollback` |
| HTTP (machines) | `GET /api/v1/sync/machines` · `PATCH /api/v1/sync/machines/self` · `DELETE /api/v1/sync/machines/{id}` |
| HTTP (key) | `GET /api/v1/sync/key/fingerprint` · `POST /api/v1/sync/key/export` · `POST /api/v1/sync/key/import` |
| UI | A top-level **Sync** page with three tabs — **Status** (the remote, the next round, a run button, the master-key card), **History** (every round this machine has run, as a table: when, outcome, what it applied here, what it published, the commit) and **Machines** (the registry table). Conflicts and pending confirmations appear as a banner on Status, not as a permanent tab. Status says what the vault is doing; History says what it has been doing, which one round rendered as prose cannot — a round that failed once is noise, and a round that has failed every hour since Tuesday is the answer. |

## Acceptance Scenarios

### Scenario: a changed vault converges and pushes

- **Given** a configured sync remote and a vault with a new knowledge document,
- **When** a converge round runs,
- **Then** the document is committed to the working tree, the commit is pushed
  to the configured branch, and the pointer advances to it.

### Scenario: an unchanged vault makes no commit

- **Given** a configured remote whose last round is already pushed,
- **When** a round runs and nothing in the vault or the remote has changed,
- **Then** no commit is created and the round is recorded as successful.

### Scenario: a remote addition lands in the vault

- **Given** a remote holding an `mcp_server` this vault does not have,
- **When** a round runs,
- **Then** the server is registered locally, its post-import hook has run, and
  the pointer advances past the commit that added it.

### Scenario: a remote deletion is applied

- **Given** a skill present on both machines, deleted on the other one and
  pushed,
- **When** a round runs here,
- **Then** the skill's files and its registry row are removed here, the
  credentials no remaining resource cites are released, and the deletion is
  audited.

### Scenario: a local-only document survives a round

- **Given** a knowledge document this vault created and the remote has never
  seen,
- **When** a round runs,
- **Then** the document is still present locally and is now published to the
  remote.

### Scenario: a stale machine does not resurrect a deletion

- **Given** a machine whose pointer predates a deletion the other machine made
  and pushed,
- **When** that machine runs its first round after being offline,
- **Then** the deletion is applied rather than reverted, because the machine
  made no change to that path relative to its own base.

### Scenario: concurrent edits to different parts of one document merge

- **Given** two machines that each appended a different section to one knowledge
  document,
- **When** both converge,
- **Then** the document holds both sections and no conflict is reported.

### Scenario: a real conflict stops the round without touching the vault

- **Given** two machines that edited the same lines of one document, and no
  internal model configured,
- **When** a round runs,
- **Then** the round aborts, the vault is unchanged, the pointer has not moved,
  and the status names the conflicted path and the working tree holding it.

### Scenario: an agent-resolved conflict is validated and reported

- **Given** a conflicted resource document and an internal model configured,
- **When** a round runs and the agent's resolution parses and validates,
- **Then** the resolution is applied as an ordinary merge result and the round's
  status names the path as agent-resolved.

### Scenario: an agent resolution that fails validation is not applied

- **Given** a conflicted resource document whose agent resolution leaves a
  conflict marker,
- **When** a round runs,
- **Then** nothing is applied, the round aborts as an unresolved conflict, and
  the vault is unchanged.

### Scenario: the fresher credential ciphertext wins

- **Given** one credential ref re-encrypted on both machines, the other machine's
  encryption being the older one,
- **When** the two meet in a round,
- **Then** the fresher ciphertext is what both machines hold afterwards,
  regardless of which commit is newer.

### Scenario: a new machine takes the union and deletes nothing

- **Given** a machine whose id the remote's registry does not hold, with its own
  vault, and a remote holding a different one,
- **When** the user runs `coffer sync adopt <url>`,
- **Then** everything the remote holds is added locally, everything the machine
  already held is still present, and the next round publishes both.

### Scenario: a returning machine does not resurrect what was deleted while it was away

- **Given** a machine that converged before, lost its pointer to a reinstall
  while its vault files survived, and a remote from which a skill was deleted in
  the meantime,
- **When** that machine joins the remote again,
- **Then** its id is recognised in the registry, its base is recovered from its
  own descriptor, the deletion is applied here rather than undone there, and the
  round reports that it joined as a returning machine.

### Scenario: a returning machine with an empty vault does not publish the loss

- **Given** a machine that converged before and whose vault was wiped, rejoining
  a remote holding hundreds of documents,
- **When** a round runs,
- **Then** nothing is pushed as a deletion, the round is recorded as awaiting
  confirmation naming how many documents it would remove from the remote, and
  the user can instead rebuild this machine from the remote.

### Scenario: a damaged machine rebuilds from the remote instead of publishing its loss

- **Given** a machine whose vault was wiped and whose round is held by the
  publish-side guard,
- **When** the user rebuilds it from the remote,
- **Then** the vault holds what the remote holds, documents only this machine
  had are gone, nothing was pushed, and the held round is cleared.

### Scenario: a failed apply holds the path back instead of deleting it

- **Given** a round in which one resource document cannot be applied here,
- **When** the next round exports the vault,
- **Then** that document is still present in the working tree, it is not
  committed as a deletion, and the round retries it.

### Scenario: an oversized deletion is held for confirmation

- **Given** a diff that would delete more documents than the circuit breaker
  allows,
- **When** a round runs,
- **Then** nothing is applied, the round is recorded as awaiting confirmation
  with the list of documents it would remove, and `coffer sync confirm` applies
  it while rejecting it leaves the vault untouched.

### Scenario: a round can be rolled back

- **Given** a completed round that applied a diff,
- **When** the user rolls it back,
- **Then** the vault returns to the state the pre-apply snapshot holds and the
  pointer returns with it.

### Scenario: memory overrides travel but the derived tree does not

- **Given** a developer who hid one fact and pinned another on one machine,
- **When** the two machines converge,
- **Then** both decisions are in force on the other machine, and nothing under
  `~/.coffer/memory/` was carried across.

### Scenario: reach stays on the machine it was set on

- **Given** an `mcp_server` present on both machines, disabled on one of them and
  restricted to a single agent on the other,
- **When** the two machines converge,
- **Then** each machine still holds the reach it was given — the disabled one is
  still disabled, the restricted one still restricted — and a later edit to the
  server's configuration on either machine reaches the other without carrying
  its reach along.

### Scenario: a channel does not travel

- **Given** a `channel` configured on one machine,
- **When** the two machines converge,
- **Then** no channel resource is registered on the other machine, and a channel
  that machine configured for itself is still there afterwards.

### Scenario: the machine registry shows every machine and cannot conflict

- **Given** two machines that have both converged,
- **When** the machines table is read on either,
- **Then** it lists both with their names, last converged day and key
  fingerprints, marks the local one, and the working tree holds one descriptor
  per machine with no merge conflict between them.

### Scenario: renaming a machine costs nothing

- **Given** a machine that has converged and appears in the registry,
- **When** the user renames it,
- **Then** nothing else in the vault is rewritten, and the new name reaches the
  other machines inside that machine's own descriptor on the next round.

### Scenario: a machine identity survives reinstalling Coffer

- **Given** a machine whose `~/.coffer` is deleted and Coffer reinstalled, on a
  host that exposes a stable identifier,
- **When** it adopts the remote again,
- **Then** it returns under the same machine id and its descriptor is updated
  rather than duplicated, so it rejoins as itself rather than as a stranger.

### Scenario: tidy runs only on its owner machine

- **Given** two converged machines with tidy enabled and one of them named as
  the owner,
- **When** the tidy interval elapses on both,
- **Then** a pass runs on the owner and is a no-op on the other, and the vault
  holds one rewritten topic document rather than two.

### Scenario: a tidy pass and a converge round do not overlap

- **Given** a tidy pass in progress,
- **When** a converge round starts,
- **Then** the round waits for the pass to finish before it serializes the
  vault, so the exported tree is never a half-rewritten corpus.

### Scenario: an edit outlives a tidy deletion

- **Given** a note the owner's tidy pass merged away and deleted, and the same
  note edited on the other machine before it converged,
- **When** the two meet in a round,
- **Then** the note is still present with its edit, the deletion is dropped, and
  the round does not report a conflict.

### Scenario: the push credential never reaches the repository

- **Given** a configured remote with a push credential,
- **When** a round pushes,
- **Then** the credential is absent from the repository's git config, from the
  git process's arguments, and from any recorded error text or audit payload.

### Scenario: the master key never enters the repository

- **Given** a remote configured to carry credential ciphertext,
- **When** a round pushes,
- **Then** the tree holds Fernet ciphertext and no key material, and a machine
  without the key reports those refs locked rather than failing decryption.

### Scenario: restore brings back a document deleted last week

- **Given** a remote whose history contains a skill later deleted and converged
  away,
- **When** the user runs `coffer sync restore --at <a date before the deletion>`,
- **Then** the skill is registered again and everything the vault gained since
  that date is untouched.

## Out of scope

- **Local export and import.** Deleted with this spec. Writing a bundle to a
  directory and reading one back is a wholesale overwrite with no base — the
  operation that caused the 2026-07-10 incident — and it has no place beside the
  diff-based apply. The needs it served are met without it: a new machine runs
  `coffer sync adopt`, an offline medium is a `file://` remote on a USB drive,
  and handing a copy to someone else is `git clone ~/.coffer/sync`.
- **More than one sync remote.** One rendezvous is what "one vault" means.
- **A hosted sync endpoint.** Would require a further constitutional amendment.
- **Syncing conversations, the audit log, or MCP invocation records.** They
  describe what happened on a machine; merging them is a different feature.
- **Merging two unrelated vaults into one.** First contact takes the union of
  documents; it does not reconcile two histories that never shared a base.
- **A machine × agent pair matrix.** Scope's two lists are `AND`-ed; expressing
  a different agent per machine on one resource is not supported.
