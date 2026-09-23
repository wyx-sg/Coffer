# Spec — Vault Sync

**Status**: Accepted
**Folder name**: this spec lives at `specs/vault-sync/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on.

Keep one vault across the user's own machines by converging each of them with a
git repository the user owns. A background worker commits what this vault
holds, lets git three-way-merge it against what the remote holds, and applies
the resulting difference back — deletions included. Background and alternatives
in [Vault Sync](../../../docs/decisions/vault-sync.md).

**This spec also owns machine identity.** The name says "sync", but `machine_id`
— how it is derived, that it survives a reinstall, what travels in its place,
and the registry that lists it — is specified here and nowhere else
(FR-021 … FR-031). Other specs key on it: a channel's machine binding in spec
[channels](../channels/spec.md) and the tidy owner in spec
[knowledge](../knowledge/spec.md) both name a `machine_id` this spec defines.

## Why

A developer works the same project from a laptop and a desktop. Both produce
vault state: knowledge files, skills, MCP registrations, agent configuration,
credentials. Without convergence each machine is an island, and the fix — export
here, carry the directory, import there — is a chore nobody performs often
enough for the two to stay alike.

- **FR-001**: Convergence with a user-owned git remote is a bounded exception to
  the constitution's local-first principle (0.6.0): the remote MUST be a
  **rendezvous, not a system of record**. Every machine's vault MUST stay
  complete and authoritative, so the remote can be deleted and rebuilt from any
  single machine without losing anything.

## What syncs

- **FR-002**: The markdown files under `~/.coffer/knowledge/<collection>/` and
  the master skill store under `~/.coffer/skills/` MUST converge, mirrored as
  regular files — except a folder in them that is derived output, which is
  FR-093.
- **FR-003**: Outbound, a symlink MUST be skipped rather than followed — its
  target is not vault content, and a link to a file outside the vault would
  otherwise be published — and anything under a nested `.git` directory MUST be
  skipped as another repository's internals. What was skipped MUST be logged
  once per round. Inbound, a symlink the working tree holds MUST be refused
  rather than read into the vault.
- **FR-004**: `mcp_server`, `agent`, `skill`, `knowledge`, `provider` and
  `channel` definitions MUST converge, serialized to text from SQLite, which
  stays the system of record. A resource document is identity, description and
  config — what the resource *is*. What it reaches is not in it (FR-014).
- **FR-097**: A resource document MUST be stored at a path keyed by the
  resource's **uid**, and MUST carry that uid inside it. A machine receiving a
  document MUST match it to a local resource by uid, and MUST create a missing
  one *at that uid* rather than minting its own — two machines holding one
  resource hold one identity for it.
  Keying the path by the name made a rename a deletion beside an addition, and
  the receiving machine could not tell that from a delete-and-create: it ran the
  full deletion, which released the credential nothing else cited and dropped
  the kind-owned state the row cascaded to. The name lives inside the document,
  where changing it is a modification of one file
  ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
- **FR-005**: Every kind MUST travel **except one it declares for itself**: a
  kind sets `converges=False` when its rows are derived on each machine rather
  than authored by the user, and `memory` is the only kind that does (spec
  [memory](../memory/spec.md) FR-023). The rule MUST live on the kind rather
  than as a list in the sync layer; the exporter MUST withhold such rows and the
  applier MUST ignore such a document, so a machine on an older build cannot
  deliver one either. A kind that travels MAY additionally declare that one of
  its **rows** does not, on the same terms and for the same reason (FR-093).
- **FR-006**: A `channel` document MUST travel while its adapter does not. A
  channel is an inbound surface — a port, a tunnel, a webhook URL a platform has
  been told to call — so the document names the one machine that may answer:
  `runs_on`, the `machine_id` whose daemon starts the adapter (spec
  [channels](../channels/spec.md) FR-080). The other machine therefore holds the
  channel's configuration, its credential references and its pairings, so taking
  over a bot is a rebind rather than a re-registration.
- **FR-007**: Module-owned shared state areas that belong to the vault rather
  than to one machine MUST converge: MCP capability preferences, internal engine
  settings, the agent plugin inventory, and channel peer pairings.
- **FR-008**: Channel peer pairings MUST travel as **platform identity** — chat
  id, sender id, display name, the chat's sticky agent — because a channel that
  moved to another machine without its pairings would make the owner re-pair
  from their phone on every rebind.
- **FR-009**: The active conversation pointer MUST NOT travel. Conversations are
  machine-local, and a published pointer would name a conversation the other
  machine does not have.
- **FR-010**: The plugin inventory MUST be an **inventory, not a replicator**:
  it records which plugins each agent has on each machine and MUST write nothing
  into any agent's configuration.
- **FR-011**: Credentials MUST travel as Fernet **ciphertext only**, and only
  when the remote is configured to carry it.
- **FR-012**: One machine descriptor document per machine MUST travel (FR-026).

## What does not sync (machine-local)

- **FR-013**: Logs, `coffer.db` itself, `daemon-config.json`, PID files, port
  allocations, chat history, conversations, the audit log, MCP invocation
  records, the whole of `~/.coffer/memory/` **and the `memory` partition rows
  derived from it**, and any runtime artifact MUST stay machine-local. The
  master key MUST **never** be written into the repository (FR-077).
- **FR-014**: **Reach** — a resource's `enabled` flag and its `scope` — is
  machine-local and MUST NOT travel in either direction. They read like two
  fields but they are one thing, written by one control: whether this resource
  is live here, and for which agents. Reach is set on the machine it applies to
  and each machine sets its own. Publishing it would let one machine silently
  re-answer a question another machine had already answered for itself — the
  laptop that deliberately left a server dark would find it live again after the
  desktop's next round, with nothing in the history that reads like a decision
  anyone made.
- **FR-093**: **Derived output MUST NOT converge, in either half.** A resource
  whose bytes each machine regenerates for itself — from material that already
  converges plus that machine's own machine-local state — MUST be withheld from
  the tree and MUST be ignored when a document for it arrives. This is the rule
  of FR-005 at the granularity of one **row**: a kind that otherwise converges
  MUST be able to declare that a particular row does not, the declaration MUST
  live on the kind rather than as a name the sync layer recognises, and the
  exporter and the applier MUST both consult it.
  Coffer's own generated skill `coffer-guide` is the case this exists for. Its
  text is rendered locally from the running build, the knowledge files (which
  converge on their own) and **which collections this machine has enabled** —
  and `enabled` is reach, which FR-014 keeps machine-local. So two machines
  holding identical files still render different bytes, each correct where it
  is. Converging it had each round overwrite the other machine's master folder
  and its resource row (whose `version_hash` is that folder's digest), the
  overwritten machine re-render at its next boot or curation pass, and the
  exchange repeat: a commit and an audit event per tick on both machines,
  forever, over an artifact neither machine reads from the other. **Both halves
  MUST be withheld**: the master folder under `skills/`, which FR-002 otherwise
  mirrors, and the resource document, which FR-004 otherwise publishes.
- **FR-094**: Withholding derived output MUST NOT publish its **absence**. A
  bundle written by an earlier build already carries those paths, and an export
  that converged them away would stage a deletion — the one change every
  machine acts on. A machine still running that earlier build has no rule to
  protect it and would take the deletion as leave to unlink its own live copy,
  and the resource document's deletion would reach the row's own delete guard,
  be refused, and be re-refused on every tick because a round re-derives its
  diff (FR-091). So the paths MUST be left exactly where they are: not
  published, not applied, not deleted, and never counted by the deletion guard.
  They become inert rather than tidy, which is the cheaper of the two mistakes.
  This is the opposite treatment from a withheld **kind** (FR-005), whose
  documents are cleared on purpose — those stand on nothing at the other end,
  while a withheld row's document stands on a master folder that machine wrote
  itself and still delivers.

Conversations and the audit log are excluded deliberately: they are records of
what happened *on a machine*, and a merged history of two machines' activity
would be a different feature with a different shape (see `/activity`).

## Concepts

A **vault document** is the serialized form of one piece of vault state at one
path in the working tree: a knowledge file, a skill file, a resource YAML, a
state YAML, a credential blob, a machine descriptor. A **converge round** is one
full cycle (FR-035). The **retry set** is the paths the working tree holds that
this vault has not absorbed, stored locally beside the pointer. A **machine** is
one installation of Coffer.

- **FR-015**: A vault MUST have **at most one** sync remote: a git repository
  the user owns, configured with a URL, a branch, a push credential reference,
  an interval, and whether credential ciphertext rides along. Sync MUST be
  disabled until the user configures it.
- **FR-016**: The URL and the branch become arguments to `git`, so neither MAY
  begin with `-` (git would read it as an option, and `--receive-pack=<cmd>` is
  a command) and the branch MUST pass `git check-ref-format --branch`. Both MUST
  be refused at the API, at the CLI and again by the domain object. The git
  adapter MUST fence every positional argument git lets it fence with `--` and
  MUST push an explicit `refs/heads/` refspec.
- **FR-017**: The working tree defaults to `~/.coffer/sync`. Every round mirrors
  the vault into it and may `reset --hard` it, so it MUST NOT be at, inside or
  above any vault directory (knowledge, skills, memory), nor at or above
  `~/.coffer` itself; inside `~/.coffer` only the default location is accepted,
  and a relative path MUST be refused.
- **FR-018**: An existing repository at that location MUST be adopted with its
  history intact — unless it has commits and an `origin` that is neither the
  configured remote nor one Coffer created, in which case it is someone's
  checkout of something else and MUST be refused rather than repointed.
- **FR-019**: A tree Coffer made MUST be marked in its local git config and MAY
  be repointed when the remote's URL changes.
- **FR-020**: The **pointer** is the commit this vault has provably absorbed,
  stored locally. It is the base of every diff and the only machine identity the
  algorithm needs, and it MUST NOT travel as an input to the algorithm.

## The machine dimension

### Identity is derived, the name is a label

- **FR-021**: `machine_id` MUST survive reinstalling and uninstalling Coffer. A
  machine that comes back under a new identity becomes a ghost: it rejoins as a
  stranger, its old descriptor lingers in the registry with nobody to update it,
  and anything that named it — the tidy owner, its own recovered pointer —
  silently stops meaning this machine.
- **FR-022**: `machine_id` MUST therefore be derived from the host, not
  generated by Coffer: on macOS, `IOPlatformUUID` from `IOPlatformExpertDevice`;
  on Linux, `/etc/machine-id` falling back to `/var/lib/dbus/machine-id`. It
  MUST be cached in `daemon-config.json` and recomputed if that cache is lost.
- **FR-023**: Where neither host identifier is readable, a UUID MUST be
  generated once and stored at `~/.coffer/machine-id` (mode `0600`). This one
  does **not** survive deleting `~/.coffer`, and the machine surface MUST say
  so, because such a machine reappears under a new id and the old descriptor
  must be removed by hand.
- **FR-024**: The raw host identifier MUST NOT be written into the repository —
  it is a hardware identifier. What travels MUST be
  `sha256("coffer-machine:" + raw)` truncated to 16 hex characters.
- **FR-025**: `machine_name` is a label, not a key: chosen by the user,
  defaulting from the hostname, changeable at any time at no cost, and stored
  inside the machine's own descriptor so it syncs.

### The registry is a derived view, not a synced table

- **FR-026**: Each machine MUST write exactly one document, at
  `machines/<machine_id>.yaml`, and MUST write no other machine's. Every machine
  owning a disjoint path is what makes these documents unable to conflict.
- **FR-027**: The registry MUST be whatever `machines/*.yaml` currently holds —
  a derived view, never a synced table of its own.
- **FR-028**: A descriptor MUST carry `name`, `os`, `hostname`,
  `coffer_version`, `last_converged_at`, `last_converged_commit`,
  `key_fingerprint`, and the names of the agents registered on that machine.
- **FR-029**: `last_converged_commit` MUST publish this machine's pointer, so
  the remote can hand it back to a machine that lost it (FR-044).
- **FR-030**: `key_fingerprint` MUST be the same short hash
  `GET /sync/key/fingerprint` returns, so the machines table can state directly
  that another machine's credentials cannot be decrypted here instead of the
  user comparing fingerprints by hand.
- **FR-031**: `last_converged_at` MUST be restamped **at most once per calendar
  day**, so a machine that is running but idle does not commit a heartbeat every
  round. It therefore means "last day this machine converged", and the UI MUST
  say so.

### Scope has no machine axis, because reach does not travel

- **FR-032**: `scope` MUST name agents and nothing else — `{ agents: [...] }`.
  `null` means every agent, a list restricts to it, `[]` matches nothing and is
  dormant, and an unknown agent name is legal and simply never matches. There
  MUST be no machine axis: reach is machine-local (FR-014), so a machine already
  names the resources it activates by *holding* that scope, and machine ids
  inside the scope would record the same fact a second time with two ways to
  disagree.
- **FR-033**: Removing the axis MUST NOT widen anything. A stored scope that
  named machines was, on this machine, either admitted by that list or dormant
  because of it; the migration MUST resolve each row against the machine id the
  daemon was actually using and write the answer that machine already saw,
  taking `agents: []` — dormant — whenever it cannot tell. Narrowing is visible
  and one click to undo; widening is a resource silently reaching an agent it
  was kept from.
- **FR-034**: A scope editor MUST state, where the user sets reach, that reach
  applies to this machine only and is not synced, and MUST say where a resource
  is dormant here.

A channel's machine binding is not this axis coming back. Reach is "which
agents, here" — a local answer each machine gives itself. The binding is "which
machine runs the adapter" — one answer the machines share, so it lives in the
channel's config and travels with it (FR-006). A binding records a fact no
machine can state alone, because it is about which of them acts.

## The converge round

- **FR-035**: A round MUST be these seven steps **in this order**:

  ```
  0  Repair    — if the working tree's HEAD is not the pointer, reset to the pointer
  1  Serialize — export the vault into the tree (differentially), commit as L
  2  Merge     — fetch, then merge origin/<branch> into L with base merge-base(L, R) → M
  3  Diff      — D := git diff L..M
  4  Guard     — circuit-breaker check on D; tag L as the pre-apply snapshot
  5  Apply     — apply D to the vault, path by path
  6  Publish   — push M; pointer := M; unapplied paths join the retry set
  ```

- **FR-036**: Step 0 MUST run first: where the working tree's HEAD is not the
  pointer, it MUST be reset to the pointer before anything else happens.

### Why deletion is safe

- **FR-037**: A deletion MUST be applied only when it appears in `D` as a
  deletion. A machine that merely *lacks* a document makes no change relative to
  its own base, and that MUST NOT be read as a deletion.
- **FR-038**: Export MUST write **differentially** — writing changed documents
  and removing documents the vault no longer holds — and MUST NOT clear and
  rewrite a directory.
- **FR-039**: Export MUST NOT delete a path in the retry set. A document this
  vault failed to absorb is pending, not deleted.

### The pointer advances only on absorption

- **FR-040**: The pointer MAY advance to `M` only when the round completes. Any
  path whose application failed MUST join the retry set instead, MUST be
  re-attempted next round, and MUST leave the set on success.
- **FR-041**: A path that fails because it cannot apply on this machine at all —
  an `agent` whose `config_dir` does not exist here — MUST be recorded as **not
  applicable here** rather than pending: preserved like a retry-set path, not
  retried, not reported as an error, and said to be so on the surfaces rather
  than presented as a failure the user has to chase.

### Joining a remote

- **FR-042**: A machine with no pointer is **joining**, and the round MUST tell
  a new machine from a returning one — out of the remote's registry, which
  either holds this machine's id or does not — before it does anything.
- **FR-043**: A **new machine** MUST take the union: its pointer is set to git's
  empty tree, so `D` is a diff from nothing and can structurally contain only
  additions. It takes everything the remote holds, keeps everything it already
  had, and the next round publishes both.
- **FR-044**: A **returning machine** MUST recover its base from its own
  descriptor's `last_converged_commit` and proceed as an ordinary stale-machine
  round: the three-way merge takes the remote's deletions, keeps this machine's
  edits, and nothing resurrects.
- **FR-045**: A returning machine whose vault is gone MUST NOT publish the loss.
  A reinstall that took `~/.coffer` with it leaves an empty vault and a valid
  pointer, which the merge would read as "this machine deleted everything";
  Coffer cannot tell a wiped disk from a deliberate purge, so the publish-side
  guard (FR-068) MUST stop the round and ask rather than guess.
- **FR-046**: Joining MUST be explicit and reported: whichever kind it is, the
  surfaces MUST state, before anything is applied, which case it is, when this
  machine last converged, how many documents the remote has changed since, and
  how many this vault has.
- **FR-047**: **Rebuild** MUST replace this vault with the remote's, discarding
  documents only this machine holds and pushing nothing. It is destructive on
  purpose and MUST NOT be reached without the user asking for it by name. It is
  the third answer a damaged machine needs, because confirming spreads the loss
  and rejecting refuses the same round forever.
- **FR-048**: A returning machine whose recorded base is no longer in the
  remote's history MUST be refused until the user picks: joining as new would
  resurrect what the others deleted, rebuilding would discard what only this one
  has, and there is no safe default.
- **FR-049**: The join detection MUST run whenever a round starts with no
  pointer, not only under `coffer sync adopt`, so configuring a remote on a
  machine that has forgotten its pointer cannot skip it.

## Applying a diff

- **FR-050**: For `knowledge/**` and `skills/**`, an addition or a modification
  MUST write the file and a deletion MUST remove it.
- **FR-051**: For `resources/<kind>/<uid>.yaml`, an addition or a modification
  MUST upsert through the kind-agnostic resource service with `${HOME}` expanded
  and the kind's import gate run, leaving the local resource's reach untouched
  (FR-014); a deletion MUST delete the resource. A document whose name differs
  from the local resource's MUST be applied as a **rename** of that resource,
  never as the arrival of a different one.
- **FR-052**: For `state/<area>/**`, the area's provider MUST apply the document
  and MUST remove it on deletion (FR-058).
- **FR-053**: For `credentials/<ref>.enc`, an addition or a modification MUST
  write the ciphertext subject to the freshness rule (FR-060); a deletion MUST
  delete the credential.
- **FR-054**: `machines/*.yaml` and `manifest.json` MUST NOT be applied in
  either direction — the registry is read from the tree, never projected into
  anything local, and the manifest is metadata about the tree.
- **FR-055**: Deleting a resource MUST release the credentials no remaining
  resource cites, as any other deletion does.
- **FR-056**: After the diff is applied, each kind's post-import hook MUST
  re-apply its machine-local side effects — native config projections, shims,
  skill deliveries — from current state.
- **FR-057**: A `channel` is upserted by the same row as every other kind, and
  its arrival MUST start nothing: what it carries is a machine binding, and a
  machine that is not the one named simply holds the document. The channel
  kind's own registration checks MUST be relaxed for exactly that case (spec
  [channels](../channels/spec.md) FR-080), because a channel bound elsewhere is
  not judged here against agents this machine happens to have.
- **FR-058**: A state document reaches the working tree only while there is a
  **decision to carry**, so its deletion is that decision being taken back. Each
  state area's provider MUST define what deleting its own document means in that
  area's terms and MUST honour it; sync MUST apply the deletion through the
  provider and MUST NOT interpret it for any area. The same rule binds the other
  direction: an area MUST NOT publish a document for its own defaults, or a
  machine that took its choice back and a machine that never made one would add
  and delete the same document at each other every round. The areas that exist
  today state their own terms in spec [mcp-gateway](../mcp-gateway/spec.md)
  (capability preferences), spec [internal-engine](../internal-engine/spec.md)
  (engine settings) and spec [agent-registry](../agent-registry/spec.md) (the
  plugin inventory).
- **FR-059**: Per-path failures MUST be reported and MUST NOT abort the round.

A binding that names no machine any registry claims is a fault on the channel,
not permission for this one to start its adapter: spec
[channels](../channels/spec.md) FR-080 owns that rule and the fail-closed
startup behaviour behind it.

## Conflicts

Most concurrent edits are not conflicts: git merges different hunks of one file
without help. What follows governs the remainder.

- **FR-060**: Credential blobs MUST NOT reach a text merge. A Fernet token
  carries its encryption time in cleartext, so two ciphertexts for one ref can
  be ordered without the key, and the **fresher encryption wins**. This rule
  applies to `credentials/*.enc` and to nothing else.
- **FR-061**: Where an internal model is configured, a bounded agent pass MAY
  resolve the remaining conflicts **in the working tree only**, and MUST NOT run
  against the live vault.
- **FR-062**: That pass's output MUST pass a validation gate — the document
  parses, a resource document validates, and no conflict marker remains — before
  it is treated as an ordinary merge result.
- **FR-063**: Resolutions MUST always be reported with their paths, whether or
  not they succeeded: a silent machine merge of the user's own notes is
  precisely what the user would want to know about.
- **FR-064**: Otherwise the round MUST abort — with no model configured, or when
  the pass fails or its output fails the gate. The vault MUST NOT be touched,
  the pointer MUST NOT move, and the surfaces MUST name the conflicted paths and
  the working tree that holds them.

## Safety

Bidirectional convergence writes the vault without a human in the loop, so two
guards are normative.

- **FR-065**: Step 4 MUST tag `L` as the pre-apply snapshot, whose tree is by
  construction the vault's state immediately before the apply. Rollback MUST be
  the same machinery run backwards — applying `M..L`. The most recent **ten**
  snapshots MUST be kept.
- **FR-066**: A round that would **lose** more than **20%** of the documents in
  an area, or **20 or more** documents in one area, MUST NOT proceed. Both
  thresholds are fixed and MUST NOT be configurable, and nothing — no caller, no
  migration, no relocation of the layout — may skip the guard rather than
  satisfy it. What counts as a loss is FR-090.
- **FR-067**: A tripped breaker MUST be recorded as needing confirmation, the
  surfaces MUST list what it would remove, and the user accepts or rejects it.
  What is outstanding is a question about one diff, which is why a later round
  re-derives it rather than repeating it (FR-091, FR-092).
- **FR-068**: The guard MUST run in **both directions** — over what the round
  would apply to the vault, and equally over what the round's own export would
  publish as a deletion. The second direction is what stops a vault that lost
  its files to a reinstall, a failed restore or a stray `rm -rf` from publishing
  that loss and taking the other machines down with it.
- **FR-069**: On the apply side the guard MUST run over everything the round is
  about to apply — the incoming diff **and** the retry set, since a held path
  the tree has since dropped is absorbed as a deletion.
- **FR-090**: The guard MUST count what a round **loses**, not what it deletes.
  A deletion with a destination **in the same area of the same diff** is a
  **move**: it MUST NOT count towards either threshold, and it MUST NOT appear
  in the list a hold puts in front of the user, because a document that turned
  up under another name was not removed. A destination MAY be shown two ways —
  the same content id reappearing, or git's own rename detection pairing the
  two sides — and a deletion with neither counts. A pairing that crosses an
  area MUST be discarded, since the guard's unit is the area. The empty
  document is never paired on content, every empty file being identical by
  construction.
- **FR-095**: The two tests MUST be asked of git as **separate** questions: the
  diff a round applies stays rename-blind, because the vault applies one path
  at a time, and the guard's reading of the same diff MUST NOT change what is
  applied or in what order.
- **FR-096**: A vault whose last round needs a human — held for confirmation,
  conflicted, or failed to push or run — MUST say so where the user already
  is, not only on the page built for it. `coffer sync status` MUST exit
  non-zero, the web UI MUST mark its **navigation entry** for the sync page,
  and the desktop shell MUST raise it as a notification and mark its icon. A
  held vault converges no further, so a hold nobody sees is an outage that
  looks like silence: the first one in the field stood for four days.

  The web UI's mark MUST be cleared by **visiting the page**, not by the
  situation changing, and MUST NOT return for the same situation. The rounds
  are timer-driven: one broken remote is a fresh round every hour, and a
  notice that re-raised itself on each would cover every page in the app
  hourly with something the user read the first time. A mark keyed on what is
  wrong — the outcome, the error, the direction and areas a hold was raised
  over — asks once, and asks again only when the answer would be different.
- **FR-091**: A round MUST re-derive its diff even while a confirmation is
  outstanding, and MUST **release** the hold where the direction it was raised
  for no longer breaches. A latch is an unanswered question about one diff, not
  a state a vault sits in: a vault held on a question that no longer arises
  MUST converge again without anyone answering it. A diff that still breaches
  MUST stay held, and re-deriving it MUST NOT move the moment the user was
  asked.
- **FR-092**: One outstanding confirmation MUST be **one** recorded round and
  one line in the daemon log, however many times the timer re-derives it: the
  round that first reported it is re-stamped rather than joined by a second,
  and no further audit event is written. The surfaces MUST still show the
  confirmation as outstanding and still offer its answers, and answering it
  MUST produce a further round of its own.

Neither guard replaces the diff-based apply; they bound the damage of a defect
in it. A machine joining as new has no deletions in either direction and is
unaffected.

FR-090 to FR-092 are numbered out of order because ids are identities here and
are never renumbered; all three belong to this section and were added after the
two defects they answer were measured on a live vault.

## Unattended rewriters

A worker that rewrites vault content with no human approving the diff is safe on
one machine and unsafe on several. Two machines rewriting one corpus each merge
the same pair of documents into a *different* result, and git merges that
cleanly — both agree the originals are deleted, the two results are additions at
different paths — so the vault holds the same content twice with nothing
reported as a conflict.

- **FR-070**: An unattended rewriter of synced vault content MUST name **one
  owner machine**, MUST run only on the machine that setting names, and MUST be
  a clean no-op on every other. The owner MUST be **synced state**, so every
  machine agrees who it is; the knowledge **tidy** pass is the case that exists
  today and its owner travels in the `internal-engine` state document that
  already carries its switch. If the owner machine is off, no pass happens,
  which is the accepted trade for a background nicety. The retention worker is
  exempt: it prunes the audit log, MCP invocation records and conversations,
  none of which sync.
- **FR-098**: The owner MUST be **reportable and changeable**, on the same
  terms as a channel's machine binding (spec [channels](../channels/spec.md)
  FR-026), because it is the same fact in the same shape: one machine named in
  a document every machine holds.
  - A surface MUST be able to say which machine owns the pass, and MUST
    distinguish **four** states — no owner named, this machine, another machine
    in the registry, and a machine **the registry does not hold**. Only the
    last is a fault, and it MUST be reported as one rather than folded into
    "runs elsewhere": the pass then runs on no machine at all, and no other
    part of the product says so.
  - An **empty** registry MUST NOT produce that fault. A vault that has never
    converged has no registry to be absent from, and every single-machine
    install has an owner naming its own machine.
  - A user MUST be able to take the pass over on this machine, and to clear the
    owner. Clearing returns the vault to running the pass wherever the setting
    is read, which is right for a vault down to one machine and wrong for one
    that still spans several, so it MUST be an explicit choice and never a
    repair anything performs on its own.
  - The four states MUST be **derived from the setting and the registry**, not
    stored: the owner is one field, and a second field recording what that
    field means is a second thing to keep true.

  This exists because the pass failed silently in exactly the way the
  requirement above accepts and the one below does not. "If the owner machine
  is off, no pass happens" (FR-070) is the accepted trade for a machine that
  will come back; an owner naming a machine that is **gone** is not that trade,
  it is curation stopped everywhere with nothing to say why and — until this
  requirement — no way to take it back short of editing the database.
- **FR-071**: A tidy pass and a converge round MUST NOT overlap. Both write the
  vault and an export taken mid-rewrite is a torn snapshot, so they MUST take
  the same lock. A pass MUST additionally be skipped while a conflict or a
  pending confirmation is outstanding, so a rewrite is never piled onto an
  unresolved divergence.
- **FR-072**: Where the owner's pass deleted a document another machine edited,
  the **edit MUST win**: the document survives with its edit, the deletion is
  dropped, and the round MUST NOT report a conflict. A fresh edit is something a
  person or an agent just decided; the deletion is a housekeeping judgement the
  next pass will simply make again.

## Determinism and path portability

- **FR-073**: Resource and state serialization MUST be deterministic — sorted
  keys, normalized timestamps, machine-local fields stripped — so that an
  unchanged vault produces an unchanged tree.
- **FR-074**: A round with nothing to say MUST produce **no commit**, and MUST
  still be recorded as successful.
- **FR-075**: Absolute paths under `$HOME` MUST be stored against a `${HOME}`
  sentinel and expanded against each machine's home — in resource documents and
  in state documents alike.
- **FR-076**: Paths outside `$HOME` MUST be stored verbatim. They may fail to
  apply on another machine, which MUST surface as a per-path failure (FR-059).

## Credentials

- **FR-077**: The master key MUST never be written into the repository. It is
  bootstrapped onto another machine out-of-band with `coffer sync key export` /
  `coffer sync key import`.
- **FR-078**: A machine holding ciphertext without the key MUST report those
  refs **locked** rather than failing decryption silently.
- **FR-079**: The push credential MUST be resolved from the credential store at
  push time, named by reference and never by value. It MUST NOT enter the
  repository's git config, MUST NOT appear in a command line, and MUST be
  redacted from any recorded error. It MUST reach git as a **credential
  helper**, which every git consults before it would prompt, and MUST NOT be
  handed over through a prompt mechanism: a prompt path is optional and
  platform-dependent — macOS's own git ignores `GIT_ASKPASS` entirely — so a
  credential delivered that way is not delivered at all on the platform Coffer
  ships a desktop app for. That failure is invisible by construction while a
  credential helper in the user's own git configuration happens to answer
  instead, and this layer pins that configuration away on purpose, so there is
  nothing left to fall back on when it stops.

## Restore

- **FR-080**: `coffer sync restore [--at <rev|date>]` MUST move the working tree
  to a revision and apply the difference from the current pointer, so a document
  deleted last week returns without discarding anything the vault gained since.
- **FR-081**: Restore MUST always be explicit; a round MUST NOT reach back into
  history on its own.

## Surfaces

- **FR-082**: The CLI MUST cover the round and the vault's lifecycle —
  `coffer sync now`, `adopt [<url>] [--keep-local]`, `status`,
  `history [--limit]`, `restore [--at <rev|date>]`, `confirm`, `reject`,
  `rebuild [--yes]`, `rollback` — and its administration:
  `remote set <url> [--branch] [--interval <seconds>] [--with-credentials] [--credential-ref]`,
  `remote show`, `remote clear`, `machine list`, `machine rename <name>`,
  `machine remove <id>`, `key export <file>`, `key import <file>`,
  `key fingerprint`.
- **FR-083**: The HTTP API MUST cover the same operations under `/api/v1/sync`:
  `GET|PUT|DELETE /sync/remote`, `POST /sync/run`, `POST /sync/adopt`,
  `GET /sync/status`, `GET /sync/runs`, `POST /sync/restore`,
  `POST /sync/confirm`, `POST /sync/reject`, `POST /sync/rebuild`,
  `POST /sync/rollback`, `GET /sync/machines`, `PATCH /sync/machines/self`,
  `DELETE /sync/machines/{id}`, `GET /sync/key/fingerprint`,
  `POST /sync/key/export`, `POST /sync/key/import`.
- **FR-084**: The web UI MUST present a top-level **Sync** page with **two**
  tabs. **Runs**, the landing tab: every round this machine has run, as a table
  — when, outcome, what it applied here, what it published, the commit.
  **Setup**: the remote, the master key and the machine registry, which are one
  errand rather than three screens. There MUST be no Status tab — what a vault
  is *doing* is the newest row of what it has *been* doing, and a separate tab
  for it put one situation in two places and made it actionable in only one.
- **FR-085**: A round waiting on the user MUST carry its answers on **its own
  row** — confirm (naming the direction, the breached areas and the paths before
  it runs), reject, and, on a `publish` hold, rebuild-from-remote. Only the round
  the vault is **currently** waiting on may carry them: `POST /sync/confirm` acts
  on the vault's present pending state rather than on a round named in the
  request. There is exactly one such row, because one outstanding confirmation
  is one recorded round (FR-092) — the timer re-stamps it rather than adding
  another each pass — and answering it produces a further round rather than
  rewriting the held one, whose outcome stays `awaiting_confirmation`.
- **FR-086**: A **conflict** MUST stay a banner above the table, because its
  paths have to be resolved with the user's own git in a working tree the table
  has no column for.
- **FR-087**: At most one row — the newest that reached its pre-apply snapshot,
  which is the round a rollback would reverse — MAY carry an **Undo** action
  naming the paths it would take back, and no other row may, because
  `POST /sync/rollback` names no round and an Undo on every row would run the
  same call from each. That row MUST carry it only when the round **applied
  something to this machine**: every round reaching the apply step tags a
  snapshot, including one that applies nothing, so after a single quiet round
  the newest snapshot is the vault exactly as it already is, and an Undo there
  offers to restore the state it is already in. The action MUST NOT move down
  to an older round that did apply something — the quiet round's snapshot is
  the newest, so the daemon would reverse to that one and leave the older
  round standing, which is a button naming one round and undoing another.
  Reaching further back is `coffer sync restore` (FR-088).
- **FR-088**: Restoring at a point in time MUST stay a CLI operation and no page
  may offer it: `--at` names a revision in the *remote's* history, which no route
  exposes, so a page could only offer a blind date box with no preview of what
  would come back.
- **FR-089**: Consecutive rounds that changed **nothing** — no documents either
  way, no join, no failure, no locked ref — MUST be folded into one row reporting
  the span and the count. They are the majority, and one row each buries
  everything that matters; they MUST NOT be dropped, because they are the only
  evidence that a vault which stopped converging on Tuesday is not simply a vault
  with nothing to do. A round that failed once is noise; a round that has failed
  every hour since Tuesday is the answer.

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

### Scenario: a symlink in the vault is skipped rather than published

- **Given** a knowledge collection holding a symlink to a file outside the
  vault,
- **When** a round serializes the vault,
- **Then** the working tree holds no copy of that file, the link is not
  followed, and the round logs once what it skipped.

### Scenario: a kind that declares itself derived never reaches the tree

- **Given** a vault with `memory` partition rows, whose kind declares
  `converges=False`,
- **When** a round exports the vault,
- **Then** no `resources/memory/*.yaml` document is written, and a document of
  that kind arriving from the remote is ignored rather than applied.

### Scenario: a locally generated skill is neither published nor overwritten

- **Given** two machines holding the same knowledge files, one with a
  collection enabled and the other with it disabled, so each has rendered its
  own `coffer-guide` master folder and registered its own `skill:coffer-guide`
  row,
- **When** both converge, and then converge again,
- **Then** neither machine's `SKILL.md` or row has been changed by the other,
  the remote carries neither `skills/coffer-guide/` nor
  `resources/skill/coffer-guide.yaml`, the second round publishes and applies
  nothing, and the knowledge files and an ordinary imported skill converge as
  usual.

### Scenario: a working tree pointed inside the vault is refused

- **Given** a request to configure the working tree at a knowledge directory, or
  at `~/.coffer` itself, or at a relative path,
- **When** the remote is configured over REST or from the CLI,
- **Then** each is refused with the reason named and no repository is created.

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

### Scenario: a state area decides what its own document's deletion means

- **Given** a state document whose area is the MCP capability preferences, and
  the other machine has taken that decision back and pushed the deletion,
- **When** a round applies the diff here,
- **Then** the area's own provider is what performs the removal, sync applies no
  meaning of its own, and the area publishes no document for its defaults, so
  the next round has nothing to delete again.

### Scenario: an oversized deletion is held for confirmation

- **Given** a diff that would delete more documents than the circuit breaker
  allows,
- **When** a round runs,
- **Then** nothing is applied, the round is recorded as awaiting confirmation
  with the list of documents it would remove, and `coffer sync confirm` applies
  it while rejecting it leaves the vault untouched.

### Scenario: a re-layout publishes without asking

- **Given** a vault whose knowledge documents have all been moved into a
  subdirectory, so the diff carries a deletion and an addition of identical
  content for nearly every document in the area,
- **When** a round runs,
- **Then** the guard does not hold it, the round publishes unattended, the other
  machine absorbs the move with no confirmation of its own, and a deletion in
  the same round that no addition received is still held and listed on its own.

### Scenario: an owner naming a machine that is gone is reported, not silent

- **Given** an unattended rewriter whose owner setting names a machine the
  registry does not hold — a machine retired, reinstalled under a new identity,
  or never converged with,
- **When** a surface reports where the pass runs,
- **Then** it names that as a fault distinct from "runs on another machine",
  because the pass is running on none, and the user can take it over here.

### Scenario: a held vault says so where the user already is

- **Given** a round held at the deletion guard, so nothing converges and
  nothing is backed up until someone answers it,
- **When** the user is anywhere other than the sync page — at a terminal, on
  another page of the web UI, or with only the desktop shell in front of them,
- **Then** `coffer sync status` exits non-zero, the web UI's navigation entry
  for sync is marked, and the shell has marked its icon and raised one
  notification — once for that condition, not once per poll,
- **And** opening the sync page clears the web UI's mark, which does not
  return while the same thing is wrong, however many rounds re-raise it.

### Scenario: a re-layout that rewrites its documents publishes without asking

- **Given** a vault whose documents have all been moved to new addresses **and
  edited on the way**, which is what a layout migration does — so the two sides
  of every change differ and no content id pairs them,
- **When** a round runs,
- **Then** the guard reads git's own rename detection, does not hold the round,
  and the other machine absorbs the migration with no confirmation of its own.

### Scenario: a wiped area is held although rename pairings are consulted

- **Given** a vault that has lost every document in an area with nothing added
  in their place — a wiped disk, a failed restore, a stray `rm -rf`,
- **When** a round runs,
- **Then** there is nothing for a pairing to match, the round is held on the
  publish side, and the loss is not published to the remote.

### Scenario: a hold is released once its diff no longer breaches

- **Given** a vault held at the deletion guard whose documents have since come
  back, so the diff that raised the hold no longer breaches it,
- **When** the next round runs,
- **Then** the hold is released without anyone answering it, the round converges
  normally, and nothing is left waiting on the user.

### Scenario: an unanswered confirmation is reported once, not once a tick

- **Given** a vault held at the deletion guard and a timer that runs a round
  every interval,
- **When** several rounds run with nobody answering,
- **Then** the history holds **one** round for it rather than one per tick, the
  audit log holds one event, the Sync page still shows the confirmation as
  outstanding with the moment it was raised, and answering it produces a further
  round.

### Scenario: a round can be rolled back

- **Given** a completed round that applied a diff,
- **When** the user rolls it back,
- **Then** the vault returns to the state the pre-apply snapshot holds and the
  pointer returns with it,
- **And** a round that applied nothing here offers no Undo at all, because the
  snapshot it left is the state the vault is already in.

### Scenario: reach stays on the machine it was set on

- **Given** an `mcp_server` present on both machines, disabled on one of them and
  restricted to a single agent on the other,
- **When** the two machines converge,
- **Then** each machine still holds the reach it was given — the disabled one is
  still disabled, the restricted one still restricted — and a later edit to the
  server's configuration on either machine reaches the other without carrying
  its reach along.

### Scenario: a rename travels as a rename

- **Given** a resource that both machines hold, whose config cites a credential,
  and which the receiving machine has given a reach of its own,
- **When** the user renames it on one machine and the two converge,
- **Then** the other machine holds the same resource under the new name — not a
  new resource — with its credential still in the store, its kind-owned state
  intact, and the reach that machine set for itself unchanged,
- **And** this holds whichever way the new name sorts against the old one,
  because the ordering of the paths a round applies must not decide whether a
  rename is lossless.

### Scenario: a path under the home directory applies on a machine with a different home

- **Given** a resource whose config names a path under this machine's home,
- **When** the document reaches a machine whose home directory has a different
  name,
- **Then** the stored document carries the `${HOME}` sentinel rather than either
  literal path, and the applied resource names the second machine's own home.

### Scenario: a channel travels and runs only on the machine it names

- **Given** a `channel` configured on one machine and bound to it,
- **When** the two machines converge,
- **Then** the channel is registered on the other machine with its binding
  intact, that machine starts no adapter for it, and the machine it names still
  runs it.

### Scenario: a channel's pairings travel with it

- **Given** a paired `channel` on one machine,
- **When** the two machines converge and the channel is rebound to the other,
- **Then** the owner's pairing is present on the machine that now runs it and no
  re-pairing is asked for, and the conversation pointer each machine holds is
  its own.

### Scenario: a synced channel carries a credential reference, never a secret

- **Given** a `channel` whose configuration cites credential refs for its bot
  token and signing secret,
- **When** a round exports the vault,
- **Then** the channel's document in the working tree holds the refs and no
  secret material, and the secrets themselves appear only as Fernet ciphertext
  and only when the remote is configured to carry credentials.

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

### Scenario: the raw host identifier never reaches the repository

- **Given** a machine whose id is derived from a host identifier,
- **When** it publishes its descriptor,
- **Then** the working tree holds only the truncated hash of that identifier and
  the raw value appears nowhere in the repository.

### Scenario: tidy runs only on its owner machine

- **Given** two converged machines with tidy enabled and one of them named as
  the owner,
- **When** the tidy interval elapses on both,
- **Then** a pass runs on the owner and is a no-op on the other, and the vault
  holds one rewritten document rather than two.

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
  git process's arguments, and from any recorded error text or audit payload,
- **And** it still authenticates, because it reaches git as a credential helper
  reading it from the environment rather than as an answer to a prompt.

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
- **A machine × agent pair matrix.** `scope` has one list, `agents`, and no
  machine axis to pair it with (FR-032). Expressing "these agents on the
  desktop, those on the laptop" inside one travelling field is not supported and
  is not wanted: reach is machine-local (FR-014), so each machine already
  answers that question for itself by holding its own scope.
