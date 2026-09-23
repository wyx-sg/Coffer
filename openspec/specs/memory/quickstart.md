# Quickstart — Memory

Coffer reads each agent's own memory, never writes it, distils it into **notes
of its own**, and hands every agent the index of that set at session start. You
do not file anything here: the partitions, the notes and the index all appear
on their own from what your agents learned. What you do is install delivery,
and occasionally look. See [`spec.md`](spec.md) and
[Aggregate Agent Memory, Never Write It](../../../docs/decisions/aggregate-agent-memory-never-write-it.md).

## Nothing to create

A **partition** — one per repository, plus one named `global` — is created by
an aggregation pass, not by you. The pass runs on the daemon's own interval and
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
source file whose content has not changed, and writes what it read — verbatim —
into each partition's hidden `.raw/`. It never touches an agent's own memory
files. If one agent's format has changed under Coffer, that agent's failing
sources are reported by path and the other agent's pass still completes.

**A partition is a repository, not a directory.** A worktree, a second clone
and the main checkout all contribute to one partition; a working directory that
is not inside a repository at all — a dated scratch folder a session happened
to run in — gets no partition, and what was learned there is judged on its
merits by the distil pass and either kept in `global` or not kept.

## Looking at what is there

```bash
coffer memory notes coffer                     # every note in the `coffer` partition
coffer memory notes global
coffer memory note coffer python-lockfile      # one note: body and the entries behind it
coffer memory retired coffer                   # what was retired, and why
coffer memory partitions --json
```

`note` prints Coffer's own text plus each origin — which agent, and the
absolute path of the native file it came from — so a note that reads wrong is
always traceable back to the thing that said it. The note is a **paraphrase**;
the agent's own words are in `.raw/`, which is what the origins point at.

A partition is also just a folder, and you can read it as one — the same two
verbs `coffer knowledge` uses:

```bash
coffer memory ls coffer                        # the partition's own directory
coffer memory read coffer notes/python-lockfile.md
coffer memory read coffer MEMORY.md --json     # paths for an editor to open
```

A partition holds four things:

| | |
|---|---|
| `MEMORY.md` | the index — one line per note, and what a session is given |
| `notes/` | Coffer's own notes, one topic per file |
| `RETIRED.md` | what was retired and why |
| `.raw/` | what was read out of the agents, verbatim and hidden |

Everything under `~/.coffer/memory/` is derived, so all of it is read-only
through Coffer: an edit here would survive only until the next pass. The files
are plain Markdown on your own disk, so `ls ~/.coffer/memory/coffer/notes/`
works too. The web UI presents a partition as a file tree with a read-only
preview beside it; there is no in-app editor, for the same reason.

## Turning what was read into notes

The **distil** pass is where the layer earns its keep. It reads the entries
aggregation left under `.raw/` and, for each one, does exactly one of four
things: folds it into a note that already covers the subject, opens a new note,
retires a note it contradicts, or keeps nothing from it. It runs unattended
too, and you can run it over one partition by hand:

```bash
coffer memory distil coffer
```

It is what merges what two agents said twice. That merge is a judgement about
**meaning**, not about words: Claude Code and Codex never phrase anything the
same way, so the literal comparison the previous design used matched nothing at
all — 378 facts, zero merges.

Only one pass per partition may run at a time. A second request while one is in
flight is refused rather than queued — the pass rewrites the whole directory,
so two of them are two writers, not one faster pass.

With no internal connection configured the pass still produces a usable
partition, mechanically: each raw entry becomes a note of its own and the index
is written from their frontmatter. What you lose is the merging, the rewriting
and the retirement — thinner, not absent.

### Why retirement is written down

A retired note leaves `notes/` and gains a record in `RETIRED.md` saying what
replaced it and why. That file is not a bin. The material the note was built
from still lives in your agent's own memory, so **without the record the next
pass would simply re-open the note the last one removed**. `RETIRED.md` is part
of every pass's input, which is what makes a removal stick.

## Switching a partition off

A partition carries **no per-agent reach**: every enabled partition is delivered
to, and recalled by, every agent. Switching one off is the only gate, and it
stops Coffer serving it anywhere.

```bash
coffer resource disable memory coffer
coffer resource enable memory coffer
```

It used to carry a reach, defaulted to the agents it had been aggregated from —
which meant a repository's notes were withheld from the other agent working in
that same repository, the opposite of what aggregating several agents' memory is
for. Nobody had chosen those values; a default had.

`enabled` governs **what Coffer serves**, not what a process on your machine can
open. Delivery hands an agent an absolute directory path, and an agent holding
a path can read the file. That is the same thing spec
[knowledge](../knowledge/spec.md) says about collections, and it is stated
rather than implied.

Deleting a partition goes through the Resource framework, not a memory route,
so it runs the same lifecycle, audit and cascade as any other resource — and
takes the directory with it:

```bash
coffer resource delete memory coffer
```

Deleting it is safe in the sense that matters: the tree is derived, so the next
sync and distil rebuild it from the agents' own files. What comes back covers
the same subjects, in wording that may differ — the notes are a distillation,
not a copy.

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

Claude Code gets it on `SessionStart`. Codex gets its earliest per-session
event with a once-per-session guard, so the index arrives once rather than on
every prompt.

**A channel-driven turn needs none of this.** Coffer composes that turn's
system prompt itself, so the index travels with it and there is nothing to
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

The **whole index** of this repository's partition, plus what is known about
you, plus the absolute path of the directory the bodies live in:

```
## Coffer memory
Known about you:
- **Reply in Chinese** (`reply-in-chinese.md`) — this project's conversations are answered in 简体中文.
...
Memory for this repository — partition `coffer` (/Users/you/WorkEnv/AI/Coffer):
- **Worktree development** (`worktree-development.md`) — always develop in a git worktree; a shared checkout is edited by other sessions concurrently.
...
Each line names its note's file. The bodies are Markdown files in /Users/you/.coffer/memory/coffer/notes — read one as a file, the way you read your own memory.
```

It names no tool, because it does not need one: every agent that receives this
reads files already — including a channel-driven turn, which drives a local
Claude Code or Codex rather than answering from the daemon. You can see exactly
what an agent would get:

```bash
coffer memory context --agent-uid <agent uid> --cwd "$PWD"
```

This is the same command the installed hook runs, which is why it fails
silently by design: if the daemon is not running or is slow to answer, it
prints nothing and exits 0 rather than breaking a real session.

A ceiling applies, sized for an index rather than for a handful of lines. When
it binds, this repository's lines are kept in preference to `global`'s, the
oldest go first, and the payload says how many were dropped and which directory
holds them — a small loss, because every dropped line is still a file.

### Finding a note in another project

```
coffer__recall(query: "unreachable internal mirror")
```

The one MCP tool this layer adds, and it is a **locator**: it answers with the
absolute paths of the notes that match, and you read the file. Use it for a
partition your session was *not* opened in — this one's whole index is already
in front of you. Matching is a case-insensitive literal substring scan, so give
it a distinctive word or phrase rather than a question. It needs no internal
connection and sends nothing anywhere.

There is no `remember` tool. An agent records something by recording it the way
it already does; Coffer reads that on its next pass.

## The REST surface

Everything above is also `/api/v1/memory/*`, specified in
[`contracts/api.openapi.yaml`](contracts/api.openapi.yaml). Partition
deletion is not among them: it is the kind-agnostic
`DELETE /api/v1/resources/{uid}`.

## Switching the unattended passes off

Both passes are on by default, and both read their switch and interval per pass
rather than at boot, so a change takes effect without restarting the daemon.
They live on the installation-wide engine settings the web UI's Settings page
edits, alongside knowledge's tidy — not on a memory-specific surface.
