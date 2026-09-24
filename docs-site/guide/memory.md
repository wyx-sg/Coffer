# Memory

Every agent you run keeps its own memory, and none of them can see any of the others'. Claude Code accrues one Markdown file per topic per project; Codex distils its rollouts into task groups and a profile. Both do it well, and neither leaves its own directory — so you end up teaching each agent what the other already learned this morning.

::: tip Experimental feature
This is an [experimental feature](/guide/experimental-features) (`memory`): off by default in a release build, on in a build from source. Switch it on under **Settings → General → Experimental features**, or with `coffer daemon features enable memory`.
:::

**Memory** is Coffer reading those native memories, distilling them into **notes of its own** — one topic per file, filed by repository — and handing each session the **index** of that set, with the absolute path to read the bodies the same way an agent reads its own memory: as files. The whole layer answers to one rule: **Coffer aggregates memory, it does not own it.** Nothing here writes into an agent's own memory files, ever. Everything under `~/.coffer/memory/` is *derived* — delete the directory, run the two passes, and an **equivalent** set comes back — which is exactly what makes it safe to rewrite aggressively.

Equivalent, not identical. The product is a distillation rather than a copy, so a rebuild covers the same subjects from the same sources in wording that may differ. The part that *is* byte-reproducible is `.raw/`, which is what a note's provenance points at.

## Memory is not knowledge

[Knowledge](/guide/knowledge) holds what you or an agent **wrote down about the world**: a platform's API contract, a service's owner, an uploaded PDF. Memory holds what agents **learned while working**: your preferences, a project's decisions, a trap already hit. They differ in every dimension that shapes a design, which is why they are two layers rather than one store with a flag.

| | Memory | Knowledge |
| --- | --- | --- |
| Where it comes from | your agents' native memories, read-only | you write it, or upload it, or an agent files it |
| Partitioned by | repository (and `global`) | collection |
| Who writes the stored text | **Coffer**, distilling | you and Coffer's curation pass, together |
| How an agent gets it | **push** — the whole index, at session start | **pull** — the agent opens the skill and reads |
| How a wrong entry is fixed | retirement, recorded so it sticks | you edit or delete the document |
| If the store is lost | rebuilt, equivalently, from the agents' own copies | gone |

## Where the notes come from

An aggregation pass reads every **registered and enabled** agent, from a path under that agent's own registered `config_dir` (`~/.claude`, `~/.codex`, or wherever you pointed it). Two readers exist today:

- **Claude Code** — one Markdown file per topic under `<config_dir>/projects/<project>/memory/`. Its frontmatter already carries a `name`, a `description` and a `metadata.type`, so nothing is derived. Claude Code's own `MEMORY.md` index is skipped, and so is anything typed `reference`: that is knowledge the agent wrote down about the world, not something it learned, and it belongs to the other layer.
- **Codex** — `<config_dir>/memories/MEMORY.md`, whose task groups each record the working directory they apply to, plus the distilled profile beside it at `memory_summary.md`. A group's user preferences, reusable knowledge and failures become entries; its own rollout references and roll-up sections do not. The summary's `What's in Memory` section is read for one thing: the **search terms** Codex states per task group. Those travel with the entry, because the source has already answered "what would you look this up by" better than any later guess — and they end up restated in the index line.

Coffer reads **no transcripts, rollouts or raw capture files** — both agents already distil their own, better than Coffer would, and this layer starts from that output. A source file whose content hash has not changed since the last pass, and whose entries are still on disk, is not read at all, so a pass over an idle machine parses nothing. If one agent's format changes under Coffer, that reader fails loudly and *in isolation*: the failing source is reported by path, the other agent's pass still completes, and notes from earlier passes are left standing rather than deleted.

What a pass writes is the partition's hidden `.raw/`: the entries **verbatim**, one file each, and nothing else. Notes, the index and the retirement record belong to the other pass.

## Partitions

A partition is a top-level directory under `~/.coffer/memory/` and one `memory` Resource. There is exactly one per **repository**, plus one named `global` — no other axis exists.

**A partition's identity is the repository, not a path.** Its Resource config records two fields: `repository_key`, which is `remote:<host>/<path>` when the repository has an `origin` and `path:<abs>` when it has none, and `repository_path`, the absolute root. That is what makes a git worktree and a second clone resolve to the partition their main checkout contributes to — a session opened in `coffer/.claude/worktrees/x` is a session about `coffer`. A working directory **inside no repository** — a dated scratch folder a session happened to run in — gets no partition at all; its entries are filed into `global`'s `.raw/` for the distil pass to keep or discard on their merits.

The name is a readable slug, never an opaque id: `/Users/you/work/coffer` becomes `coffer`. It is taken from the remote's last segment where there is one, so two clones under different local directory names agree rather than racing to create two partitions. A name already claimed is disambiguated by prefixing a parent path segment — `work-api` and `personal-api` — with a numeric suffix only as the last resort when every ancestor is taken too. The absolute repository path is recorded on the Resource and restated at the top of the partition's `MEMORY.md`, so the folder explains itself to anyone browsing it.

`global` is for notes about the person rather than a project: preferences and standing instructions, which go there whichever repository they were learned in, as does anything whose project root *is* your home directory. Partitions are created by aggregation, never by you and never by an agent's working directory at read time.

A partition whose repository is no longer on this disk is listed as **unresolvable** rather than hidden. Nothing can resolve to it any more, so it is delivered to nobody — and only you can decide whether that repository is coming back.

## Run a sync, then look

The daemon runs a pass on its own interval and one immediately at startup, so there is usually something to look at already. To force one:

```bash
coffer memory sync
```

```json
{
  "partitions": ["coffer", "global"],
  "entries_written": 62,
  "sources_read": 9,
  "sources_skipped": 141,
  "failures": []
}
```

```bash
coffer memory partitions
coffer memory notes coffer
coffer memory note coffer python-lockfile
coffer memory retired coffer
```

```
Memory partitions
name     notes   repository
coffer      48   /Users/you/work/coffer
global      14
```

`note` prints Coffer's own text plus every origin: which agent, and the absolute path of the native file the entry was read out of. The body is a **paraphrase**, not a quote, so a note that reads wrong has to be traceable back to the thing that actually said it — and it is, twice over: through the origin's native path, and through the verbatim entry under `.raw/`.

Two agents that recorded the same lesson produce **one** note naming both. That match is a judgement about *meaning*, made by the distil pass, not a comparison of words: measured on a live vault, 378 entries from two agents produced **zero** matches under literal comparison, because Claude Code and Codex never phrase anything the same way.

## A partition is a folder

You can read one as exactly that, with the same two verbs `coffer knowledge` uses:

```bash
coffer memory ls coffer
coffer memory read coffer notes/python-lockfile.md
coffer memory read coffer MEMORY.md --json      # with absolute paths for an editor
```

`ls` prints the whole tree rather than one level, because a partition is two levels deep by construction:

```
~/.coffer/memory/<partition>/
  MEMORY.md          the index — one line per note, and what a session is given
  notes/<slug>.md    one note, frontmatter first
  RETIRED.md         what was retired and why, once anything has been
  .raw/              what was read out of the agents, verbatim and hidden
```

Four files, four jobs, **one writer each**: `.raw/` is aggregation's and only aggregation's, and `notes/`, `MEMORY.md` and `RETIRED.md` are the distil pass's. That split is what lets a bad distillation be re-run without going back to the agents.

Each note file's frontmatter carries its title, its one-line description, its type (`user`, `feedback` or `project`), its origins, any search terms its sources supplied, and `created_at` / `updated_at`. There is **no status field and no `superseded_by`** — a note a later one contradicts leaves `notes/` rather than sitting there marked dead.

Both commands are read-only, and so is the web UI's file pane — not a missing feature: the tree is derived, so an edit here would survive only until the next pass. If a note is wrong, fix it where it came from. `.raw/` is reachable through the same tree but marked **derived input**, because those files are the agents' words rather than Coffer's answer.

## The distil pass

Distil is where the layer earns its keep. It reads the entries aggregation left under `.raw/` and, for each one, does exactly one of four things: **merge** it into a note that already covers the subject, **open** a new note, **retire** a note it contradicts, or **keep nothing**. Then it rewrites `MEMORY.md` — on every path, even when nothing changed, because the index *is* the delivery and a partition with notes and no index delivers nothing.

```bash
coffer memory distil coffer
```

```json
{
  "partition": "coffer",
  "merged": 3,
  "opened": 1,
  "retired": 1,
  "dropped": 2,
  "model_used": true
}
```

The pass is incremental in a specific sense: **no single request carries the partition's bodies.** Routing sends this round's new entries, the existing notes as **index lines only**, and the retirement record, and gets back one action per entry. Writing then sends **one** note's body plus the entries routed to it, one request per note actually touched. A partition of a hundred notes that gained three entries costs one routing request over a hundred index lines and at most three small writing requests — never a hundred bodies.

Only one pass per partition may run at a time. A second request while one is in flight is **refused** (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued: the pass rewrites the whole directory, so two of them are two writers, not one faster distil. The unattended sweep claims the same lock and simply skips a partition the button already holds.

With no internal model connection configured the pass runs **mechanically**: each raw entry becomes a note of its own, carrying the source's own title, description, text, type and search terms, and `MEMORY.md` is written from that frontmatter. `model_used` comes back `false`. Nothing is merged and nothing is retired, because both are judgements about meaning — what you get is a real partition, thinner rather than absent, and no model is called on any path.

### Why a retirement is written down

A retired note leaves `notes/` and gains a record in `RETIRED.md` naming its title, the reason, and the note that replaced it when there was one. That file is not a bin — **it is the mechanism**. The material the note was built from still lives in your agent's own memory, outside anything Coffer controls, so the next aggregation reads it again and, without the record, the next pass re-opens the note the last one removed. In a store whose sources live outside it, an unrecorded deletion is undone. `RETIRED.md` is part of every pass's input, which is what makes a removal stick.

It also accounts for the fourth action. An entry a pass kept nothing from gets a record with no slug, naming the entry ids it excludes, because `.raw/` may not be pruned to express that — and without it the same entry would be sent to the model on every pass for the rest of the vault's life.

## What an agent actually receives

At session start, the **whole index** — not a digest:

1. What is known about you: `global`'s index, one line per note.
2. The whole index of the current repository's partition, one line per note.
3. The **absolute path** of the directory those bodies live in, and the statement that a note's body is read as a file.

A line is written to be sufficient on its own — the conclusion in the line rather than a pointer to it, plus the file to open and any search terms its source supplied:

```
## Coffer memory
Known about you:
- **Reply in Chinese** (`reply-in-chinese.md`) — this project's conversations are answered in 简体中文.
Memory for this repository — partition `coffer` (/Users/you/work/coffer):
- **Worktree development** (`worktree-development.md`) — always develop in a git worktree; a shared checkout is edited by other sessions concurrently.
Each line names its note's file. The bodies are Markdown files in /Users/you/.coffer/memory/coffer/notes — read one as a file, the way you read your own memory.
```

**Nothing in the payload names a tool, and that omission is deliberate.** Every consumer of it is a local process with filesystem access: a hook-driven Claude Code session, a hook-driven Codex session, and a channel-driven turn, which drives a local agent rather than answering out of the daemon. All three reach their own memory with an ordinary file read already. The previous design sent eight lines and a tool name, and in three weeks no agent followed the pointer once.

One renderer writes both `MEMORY.md` and the delivered line, and one definition of "newest" sorts both, so the file and the payload can never say the same note two different ways.

A **ceiling** applies — `12000` tokens, sized for an index rather than for a handful of lines. For scale: Claude Code loads its own 94-entry index, about 9k tokens, into every session of its own accord; this vault's `coffer` index is ~3k and its `global` ~1.5k, so the ordinary payload is far below the ceiling and the ceiling is a guard rather than a budget that binds. When it does bind, the **current repository's lines are spent first** and `global` gets what is left — the reverse of the previous design, which filled ~600 tokens with `global` first and, on a live vault of 189 entries, delivered 8 lines of which none were about the project the session was open in. The *text* still opens with `global`, because it is short and it frames what follows; only the spending order is reversed. A trim drops the oldest lines and leaves a notice naming how many and the directory they are in:

```
(12 older line(s) not shown — those notes are files in /Users/you/.coffer/memory/coffer/notes)
```

That notice is reserved before any note line is considered, so a trim can never crowd out the line announcing it. With nothing to deliver the payload is empty rather than a bare header. See exactly what an agent would get — the same command the installed hook runs, which takes the agent's uid (`coffer agent show claude-code` prints it):

```bash
coffer memory context --agent-uid <agent uid> --cwd "$PWD"
```

**A channel-driven turn needs no setup at all.** Coffer composes that turn's system prompt itself, so the index travels with it — and when there is nothing to deliver the turn carries no memory header rather than an empty one.

### Finding a note in another partition

`coffer__recall` is the one MCP tool this layer adds, and it is a **locator**, not a reader:

```
coffer__recall(query: "unreachable internal mirror")
```

It answers with each match's **absolute path**, title, description, type and partition — never the body, because the caller reads the file. Matching is a case-insensitive literal scan over each note's body, title, description and search terms, across every **enabled** partition, whoever is asking; up to ten locations come back, sorted by path, with no score, no mode and no model involved and nothing sent anywhere. A retired note can never come back from it: retirement takes the file out of `notes/`, and this reads `notes/`.

Give it a distinctive word or phrase rather than a whole question, and reach for it for a partition your session was *not* opened in — this one's whole index is already in front of you. There is no `remember` tool: an agent records something by recording it the way it already does, and Coffer reads that on its next pass.

## Installing delivery

For an agent you drive yourself, the index arrives through that agent's own hook mechanism, and installing one writes an entry into that agent's **settings** file. A hook is not memory — it is the file that already carries your `env`, your `permissions` and every other hook you wired up — but it is still that agent's own configuration, so Coffer never touches it silently. It is an explicit act, per agent:

```bash
coffer memory delivery                      # who has it, who does not
coffer memory delivery-install claude-code
coffer memory delivery-remove claude-code
```

```
Memory delivery
agent         installed   event              command
claude-code   True        SessionStart       : coffer-memory; coffer memory context --agent-uid 01J… --cwd "$PWD"
codex         False       UserPromptSubmit   : coffer-memory; f="${TMPDIR:-/tmp}/.coffer-memory-fired-$PPID"; …
```

Claude Code gets it on `SessionStart`, in `~/.claude/settings.json`, matching all four ways a session begins (`startup|resume|clear|compact`). Codex has no session-start event at all — its five hook events are `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop` and `UserPromptSubmit`, read out of the installed binary rather than assumed — so it gets the earliest of those, in `~/.codex/hooks.json`, with a once-per-session guard: a lock file keyed on the invoking process, so the index arrives once rather than on every prompt.

Every entry carries Coffer's own marker (`: coffer-memory;`) as the argument of a leading no-op, so detection never depends on the CLI's binary name: installing twice leaves one entry and removing takes out only Coffer's, dropping a now-empty event array and an empty `hooks` object behind it. Every hook you or another tool wired onto the same event is left exactly as it was, as is every other event and every unrelated key. The command itself is built to fail quietly: if the daemon is not running, or is slow to answer within three seconds, `coffer memory context` prints nothing and exits 0 rather than breaking a real session.

### Installed is one question; fired is another

The delivery listing answers exactly one thing — installed or not. It carries **no last-fired timestamp**, on purpose. Whether the hook has run is not a property of the agent but a stream of events, and it is recorded as one, on the vault-wide audit surface:

```bash
coffer audit list --event-type memory_delivery_fired --kind agent --name claude-code
```

That split is a reaction to a specific failure. Coffer shipped a session-context injection layer once, it worked, it was never actually installed on the maintainer's own machine, and nothing said so for two months. The fix is not a warning light on the agent's page: a hook installed a minute ago has legitimately never fired, and a surface that flags that is crying wolf about its own normal state. The fix is that every fire is an event you can go and read, recorded with the agent as both the resource and the actor. `memory_aggregated`, `memory_distilled`, `memory_delivery_installed` and `memory_delivery_removed` are recorded the same way, each with the actor that caused it — so a scheduled pass is distinguishable from one you asked for.

## Switching a partition off, and deleting it

A partition carries **no per-agent reach**: every enabled partition is served to every agent, on delivery and on recall alike. It used to carry one, seeded with the agents it had been aggregated from — which meant a repository's notes were withheld from the other agent working in that same repository, the exact opposite of what aggregating several agents' memory is for. Switching a partition off is the one gate left, and it stops Coffer serving it anywhere.

```bash
coffer resource disable memory coffer
coffer resource enable memory coffer
coffer resource delete memory coffer        # lifecycle is a Resource concern
```

`enabled` governs **what Coffer serves**, not what a process on your machine can open: delivery hands an agent an absolute directory path, and an agent holding a path can read the file. Deleting takes the directory with it, and is safe in the sense that matters here: the next sync and distil rebuild it from the agents' own files.

::: tip The notes stay on this machine
[Sync](/guide/sync) converges the knowledge and skills trees between machines. It carries **nothing** of memory: not the tree under `~/.coffer/memory/`, and not the partition rows either — `memory` is the one resource kind that declares `converges=False`. These notes are distilled from the agents installed on *this* machine, so each machine derives its own from the agents it actually has, and a partition published to another would arrive there naming a repository that machine may not have cloned, with no notes behind it, until its own next pass recomputed it away. Losing the tree costs nothing — the sources it came from are still in the agents' own directories.
:::

## The unattended passes

Aggregation and distil both run on a timer and both default to **on**, for the reason everything else here is safe to repeat: a pass only reads the agents' own files and only writes the derived tree, so deleting that tree and running both again reproduces an equivalent one. Aggregation runs hourly by default and takes a catch-up pass immediately at startup, because a daemon that has just started is when its picture of the agents is most stale. Distil sweeps every six hours by default and waits about a minute after boot, so it does not spend a model on entries this boot's own aggregation was about to find anyway. Both switches and both intervals live on **Settings → Coffer's model**, under *Automatic upkeep*, alongside knowledge's curation pass, and are read per pass rather than at boot — a change takes effect without restarting the daemon.

## The CLI

| Area | Commands |
| --- | --- |
| Partitions | `partitions` · `notes` · `note` · `retired` |
| Files | `ls` · `read` |
| Passes | `sync` · `distil` |
| Delivery | `context` · `delivery` · `delivery-install` · `delivery-remove` |

Deleting a partition is a Resource operation: `coffer resource delete memory <name>`. So is switching one off: `coffer resource disable memory <name>`.

## The REST surface

| Route | Purpose |
| --- | --- |
| `GET /api/v1/memory/partitions` | Every partition, with its repository, note count and whether it still resolves. |
| `GET /api/v1/memory/partitions/{uid}/notes` | The notes in one partition. |
| `GET /api/v1/memory/partitions/{uid}/notes/{slug}` | One note, with its body and origins. |
| `GET /api/v1/memory/partitions/{uid}/retired` | `RETIRED.md`, read back, newest first. |
| `GET /api/v1/memory/partitions/{uid}/files` | The partition's own directory, as a tree. |
| `GET /api/v1/memory/partitions/{uid}/files/content?path=…` | One file out of it. |
| `POST /api/v1/memory/sync` | Run aggregation now. |
| `POST /api/v1/memory/partitions/{uid}/distil` | Run the distil pass now. |
| `POST /api/v1/memory/context` | Compose the session-start payload. |
| `GET /api/v1/memory/delivery` | Per-agent installation state. |
| `POST /api/v1/memory/delivery/{agent_uid}/install` | Install the hook. |
| `DELETE /api/v1/memory/delivery/{agent_uid}` | Remove it. |

The file family is read-only — a write is refused with 405, and a path escaping the partition with `MEMORY_UNSAFE_PATH`. A read answers with the file's absolute path and its containing folder's absolute path, so whatever you hand the answer to can open it directly. Deleting a partition is the kind-agnostic `DELETE /api/v1/resources/{uid}`; there is no memory-specific route for it.

These routes are the *owner's* view. Nothing here is filtered per agent, and neither is what an agent's own session reaches through `POST /context` and `coffer__recall` — a partition is either enabled for everyone or served to nobody. `POST /context` still takes an agent uid, but only so a fire can be recorded against it; it decides nothing about the content.

## In the web UI

Memory is one page under **Resources**. `/memory` shows the first-run welcome (with **Read from agents**) until a partition exists, and then lists partitions as a table, with each row's repository, note count and on/off control, a badge on a partition whose repository has gone missing, and **Read from agents** in the header to run an aggregation. `/memory/:uid` opens one partition as a file tree with a read-only preview beside it, with open-in-editor and reveal-in-file-manager on the previewed file, and carries the two acts that belong to the partition as a whole: switching it off, and **Distil** — which reports when a pass is already in flight rather than inviting a second one.

There are no per-note actions anywhere: a partition is a folder of derived Markdown that Coffer's own passes rewrite on their own schedule, so a verdict recorded against one note would be a promise the surface could not keep. Delivery is **not** on this page. It writes one agent's settings file, so it lives on that agent's own detail page, under its Memory tab — beside the read-only view of that agent's native memory stores, which Coffer shows you and never writes.

[Channels →](/guide/channels)
