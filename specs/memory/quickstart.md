# Quickstart — Memory

Coffer reads each agent's own memory, never writes it, and hands every agent
back what the others already learned. You do not file anything here: the
partitions, the facts and the digests all appear on their own from what your
agents distilled. What you do is install delivery, and occasionally look. See
[`spec.md`](./spec.md) and
[Aggregate Agent Memory, Never Write It](../../docs/decisions/aggregate-agent-memory-never-write-it.md).

## Nothing to create

A **partition** — one per project, plus one named `global` — is created by an
aggregation pass, not by you. The pass runs on the daemon's own interval and
starts one immediately when the daemon comes up, so on a machine with a
registered agent there is usually something to look at already:

```bash
coffer memory partitions
```

To force one now:

```bash
coffer memory sync
```

That reads every **registered and enabled** agent's native memory, skips any
source file whose content has not changed, and writes the facts into their
partitions. It never touches an agent's own memory files. If one agent's
format has changed under Coffer, that agent's failing sources are reported by
path and the other agent's pass still completes.

## Looking at what is there

```bash
coffer memory facts coffer                    # every fact in the `coffer` partition
coffer memory facts global
coffer memory fact coffer python-lockfile     # one fact: body, origins, conflicts
coffer memory partitions --json
```

`fact` prints the fact's own words plus each origin — which agent, and the
absolute path of the native file it came from — so a fact that looks wrong is
always traceable back to the thing that said it.

The files themselves are plain Markdown on your own disk, laid out as
[`data-model.md`](./data-model.md) describes, so `ls ~/.coffer/memory/coffer/facts/`
works too. The web UI presents a partition as a file tree with a read-only
preview beside it; there is no in-app editor, because the whole tree is
derived and an edit would survive only until the next pass.

## Merging duplicates and surfacing contradictions

The **organise** pass merges what two agents said twice, marks a fact
superseded when a later one contradicts it, flags a pair it cannot settle, and
rewrites the partition's `summary.md` digest. It runs unattended too, and you
can run it over one partition by hand:

```bash
coffer memory organize coffer
```

Only one pass per partition may run at a time. A second request while one is in
flight is refused rather than queued — the pass rewrites the whole directory,
so two of them are two writers, not one faster organise.

With no internal connection configured the pass still produces a usable
digest, mechanically: facts grouped by type, newest first, one line each. What
it loses is the merging and the supersession, not the feature.

## Scoping a partition

A partition is a Resource, so the framework's per-agent scope applies. Its
default scope is the set of agents it was aggregated from — memory flows back
to its own sources with no setup — and narrowing it is yours to do; a later
pass never overwrites your choice.

```bash
coffer scope show memory:coffer
coffer scope set memory:coffer --agents claude-code
coffer scope clear memory:coffer            # back to every agent
```

Deleting a partition goes through the Resource framework, not a memory route,
so it runs the same lifecycle, audit and cascade as any other resource — and
takes the directory with it:

```bash
coffer resource delete memory:coffer
```

Deleting it is safe in the sense that matters: the tree is derived, so the next
sync rebuilds it from the agents' own files.

## Installing delivery

Session-start delivery writes **one entry into an agent's own settings file**,
so Coffer never does it silently. Install it per agent:

```bash
coffer memory delivery                      # who has it, who does not
coffer memory delivery-install claude-code
coffer memory delivery-remove claude-code
```

The entry carries Coffer's own marker, so installing twice leaves one entry and
removing takes out only Coffer's — every hook you or another tool wired up on
the same event is left exactly as it was.

Claude Code gets it on `SessionStart`. Codex has no session-start event, so it
gets its earliest per-session event with a once-per-session guard: the digest
arrives once rather than on every prompt.

**A channel-driven turn needs none of this.** Coffer composes that turn's
system prompt itself, so the digest travels with it and there is nothing to
install.

### Has it actually run?

The delivery listing answers one question — installed or not. Whether the hook
has *fired* is a different fact, and it is recorded as an event, so it is read
on the vault-wide audit surface:

```bash
coffer audit list --event-type memory_delivery_fired --name claude-code
```

That separation is deliberate. The previous injection layer shipped, was never
installed, and nothing said so for two months; a hook installed a minute ago
has legitimately never fired, so the per-agent status does not warn about the
absence of a fire — the log answers it instead.

## What an agent sees

At session start, a few hundred tokens:

- **L0**, always — who you are, what this project's memory holds, and how to
  ask for more.
- **L1**, when it fits the budget — the current project's digest, one line per
  fact.

The payload is bounded by an explicit token budget, spent on `global` facts
about you first and then this project's most recent. When facts are left out it
says how many and how to reach them. You can see exactly what an agent would
get:

```bash
coffer memory context --agent claude-code --cwd "$PWD"
```

This is the same command the installed hook runs, which is why it fails
silently by design: if the daemon is not running or is slow to answer, it
prints nothing and exits 0 rather than breaking a real session.

- **L2**, on request — `coffer__recall`, the one MCP tool this layer adds:

```
coffer__recall(query: "unreachable internal mirror")
```

It takes a word or phrase, spans only the partitions the calling agent is
scoped to, and returns the matching facts **whole**, with their origins.
Matching is a **case-insensitive literal substring** scan over each fact's
body, title and description — no score, no mode, no ranking — so give it a
distinctive phrase rather than a whole question. It needs no internal
connection and sends nothing anywhere.

There is no `remember` tool. An agent records something by recording it the way
it already does; Coffer reads that on its next pass.

## The REST surface

Everything above is also `/api/v1/memory/*` — eleven routes, specified in
[`contracts/api.openapi.yaml`](./contracts/api.openapi.yaml). Partition
deletion is not among them: it is the kind-agnostic
`DELETE /api/v1/resources/memory/{name}`.

## Switching the unattended passes off

Both passes are on by default, and both read their switch and interval per pass
rather than at boot, so a change takes effect without restarting the daemon.
They live on the installation-wide engine settings the web UI's Settings page
edits, alongside knowledge's tidy — not on a memory-specific surface.
