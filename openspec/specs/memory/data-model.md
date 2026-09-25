# Data Model — Memory

The memory layer's state is a directory of Markdown files plus the one
Resource row each partition already has as a Resource. This document describes
what is on disk, the frontmatter contract, and the handful of rows and values
the surfaces answer with. Authority is [`spec.md`](spec.md) and
[Aggregate Agent Memory, Never Write It](../../../docs/decisions/aggregate-agent-memory-never-write-it.md).

## There is no memory table

**This layer adds no table of its own** ("Add no table of its own"). Notes,
raw entries, the index and the retirement record are files; the only database
presence a partition has is the row every Resource has, in the kind-agnostic
`resources` table, carrying its name, its `enabled` flag and a two-field
`config` — the repository it was learned in, and nothing else.

Everything under `~/.coffer/memory/` is **derived** ("Keep the memory tree
derived and local"). Delete it, run aggregation and distil, and an
**equivalent** set comes back: the same subjects from the same sources, not
necessarily the same wording, because the product is a distillation rather
than a copy. That is a weaker guarantee than this layer used to make, and it
is the price of the notes being Coffer's own writing. `.raw/` is the part that
*is* byte-reproducible, and it is what a note's provenance points at.

## On-disk layout

```text
~/.coffer/memory/
├── .source_state.json            # {native_path: last-seen digest} — the skip cache
├── global/                       # notes about the person, delivered wherever they work
│   ├── MEMORY.md                 # the index
│   ├── notes/
│   │   └── reply-in-chinese.md
│   ├── RETIRED.md                # present once something has been retired
│   └── .raw/                     # verbatim entries, hidden
│       └── 3f2a91c4de55b071.md
└── coffer/                       # one partition per repository, named from it
    ├── MEMORY.md                 # names the absolute repository path
    ├── notes/
    │   ├── python-lockfile.md
    │   └── worktree-development.md
    ├── RETIRED.md
    └── .raw/
```

Four files, four jobs, **one writer each** — which is what makes "Keep distil
out of the raw directory" checkable by reading the call sites rather than by
trusting a comment:

| Path | Written by | Read by |
|---|---|---|
| `.raw/` | aggregation, and only aggregation | the distil pass; the file tree, marked as derived input |
| `notes/` | the distil pass | delivery, recall, the file tree, and any agent holding the path |
| `MEMORY.md` | the distil pass | delivery, and a human opening the folder |
| `RETIRED.md` | the distil pass | **the next distil pass**, and a human |

- `~/.coffer/memory/` is the root; `$COFFER_MEMORY_ROOT` overrides it for
  tests. Path construction lives in exactly one module,
  `infrastructure/memory/paths.py`, which is also where the traversal guard
  "Confine reads to registered agents' memory paths" asks for lives
  (`check_segment` refuses an empty, hidden, all-dots or otherwise unsafe
  segment).
- `.source_state.json` is a flat `{native_path: digest}` mapping. Losing it
  costs one pass of unnecessary re-parsing, never correctness — a digest match
  alone never suppresses a rebuild.
- There is no `README.md` any more: the partition explains itself at the top
  of its own `MEMORY.md`, which is the file both a human and a session
  actually read. There is no `.history/` either — memory is never the only
  copy of anything it holds.

## Partition

A **partition** is a top-level directory under the memory root *and* one
`memory` Resource. There is exactly one per **repository** plus one named
`global`, and no other partitioning axis exists ("Partition by repository plus
global").

| Field | Where it lives | Notes |
|---|---|---|
| `name` | the directory name, and the Resource's name | A readable slug from the repository's own name — `/home/dev/coffer` → `coffer`. A collision is resolved by prefixing a parent segment (`work-api` vs `personal-api`), never by an id ("Identify a partition by its repository"). |
| `repository_key` | `Resource.config` | The identity a directory is resolved to. `remote:<host>/<path>` when the repository has an `origin` remote, so two clones agree; `path:<abs>` when it has none. Empty for `global`. |
| `repository_path` | `Resource.config`, restated at the top of `MEMORY.md` | Absolute path of the repository's main working tree. Empty for `global`. |
| `enabled` | the Resource's own column | The framework's, not this layer's. |
| `note_count` | counted from `notes/` at call time | Never stored. |
| `unresolvable` | computed at call time | True when `repository_path` no longer exists on disk. Surfaced rather than hidden, because an orphaned partition is delivered to nobody and the developer is the only one who can decide to delete it ("Report unresolvable partitions"). |

### How a directory becomes a partition

1. The reader reports the working directory an entry was learned in.
2. `infrastructure/memory/repository.py` walks up for a `.git`. A `.git`
   **directory** names the repository directly; a `.git` **file** is a
   worktree pointer, followed through its `commondir` to the main working
   tree. This is what collapses a worktree into its repository ("Identify a
   partition by its repository").
3. `origin`'s URL is read out of that repository's own `.git/config` and
   normalised by `domain/memory/repository.py` — scheme, user, port, trailing
   `.git` and trailing slash dropped, host lowercased — so
   `git@host:owner/repo.git` and `https://host/owner/repo` are one key and two
   clones land in one partition.
4. **No repository above the directory means no partition** ("Create no
   partition for a non-repository directory"). The entry is still aggregated;
   the distil pass decides on its merits whether it belongs in `global` or
   nowhere. Six of sixteen partitions on the maintainer's live vault were
   dated scratch folders created this way under the previous design.

Partitions are created by aggregation, never by the user and never by an
agent's working directory at read time ("Create partitions only by
aggregation") — the `memory` Kind sets `generic_create_allowed=False`, and
`MemoryService.aggregate` opts in explicitly. Deletion goes through the
kind-agnostic Resource route, which cleans the directory up through the Kind's
`on_delete`.

## Raw entry

One entry as a reader saw it, written **verbatim** to
`<partition>/.raw/<origin key>.md` ("Keep raw entries verbatim and hidden").
This is the layer where "the source's own words" still holds, and it is what a
note's claim is checked against when the note reads wrong.

| Field | Type | Notes |
|---|---|---|
| `title` / `description` | string | A handle for the distil pass, not a title a person reads. Claude Code supplies both; Codex supplies neither, so its reader derives them and says where it does. |
| `type` | `user` \| `feedback` \| `project` | `user` and `feedback` are *personal*: they file into `global` whichever repository they came from ("File personal entries into global"). |
| `body` | string | The source's own words. |
| `anchor` | string | Where inside the source file — a heading, a bullet's content hash — or empty when the whole file is the entry. |
| `project_root` | string | The working directory it was learned in, before repository resolution. |
| `search_terms` | list of string | What the source itself says to look this material up by. Codex states them per task group in `memory_summary.md`; Claude Code states none. Carried rather than discarded, because the source has already answered the question better than a later guess can ("Read Claude Code and Codex memory with their search terms"). |
| `agent` / `native_path` / `captured_at` | string | Where it came from and when, so the file stands alone as provenance. |

The file name is the **origin key**: `sha256(agent \0 native_path \0 anchor)`
truncated to 16 hex characters. Hashed rather than concatenated because it
travels in file names and frontmatter, and an absolute path there leaks the
shape of the user's disk into a place it does not belong.

## Note

One note is one topic, written by Coffer, at `<partition>/notes/<slug>.md`: a
YAML frontmatter block, then Coffer's own prose underneath.

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Also the file name. From the title, deduplicated within the partition. |
| `title` | string | Coffer's, not a source's. |
| `description` | string | **One line, written to be read on its own** — it *is* the index entry, and the index is what a session is given ("Store each note as one Markdown file with frontmatter", "Write each index line to stand on its own"). |
| `type` | `user` \| `feedback` \| `project` | As above. |
| `body` | string | Coffer's own writing, distilled from one or more raw entries ("Write notes in Coffer's own words"). Not a quote. |
| `partition` | string | `global` or a repository slug. |
| `origins` | list of Origin | Every raw entry this note was built from, and through them every contributing agent ("Record provenance and merge by meaning"). |
| `search_terms` | list of string | Carried up from the entries that supplied them, and restated in the index line so the next agent does not have to guess a word. |
| `created_at` / `updated_at` | string | A note accumulates; `updated_at` moves when a later pass rewrites it. |

There is **no** `status`, no `superseded_by` and no `conflicts_with`. A note a
later one contradicts does not sit in `notes/` marked dead — it leaves, and
the fact of its leaving is recorded in `RETIRED.md`. The previous design kept
superseded facts in place and then handed them back from `recall` anyway,
which made 11 dead facts on the live vault answerable as if current.

A note's **key** is the smallest of its origin keys, so a note that gains a
second origin on a later pass keeps the identity it had.

### Origin

| Field | Notes |
|---|---|
| `agent` | The registered agent's resource name, e.g. `claude-code`. |
| `native_path` | Absolute path of the native file it was read out of. |
| `anchor` | Where inside that file, or empty when the whole file is the entry. |
| `captured_at` | When Coffer read it. |
| `source_written_at` | When the source says it was written, when it says at all. |

## Retirement

`RETIRED.md` is a list: one record per retired note, and one per entry a
pass kept nothing from (empty `slug`). A note is retired either because a later
entry contradicted it or because every raw entry it was built from is gone
("Retire a note whose raw entries are all gone"):

| Field | Notes |
|---|---|
| `slug` | The file name the note had under `notes/`; empty on a record that accounts for a dropped entry rather than for a note. |
| `title` | So the record reads as prose rather than as filenames. |
| `reason` | Why it is no longer true, in Coffer's words. |
| `replaced_by` | The slug of the note that replaced it, or empty when the subject was simply dropped. |
| `retired_at` | When. |
| `entry_ids` | The raw entries the record accounts for — the retired note's own sources, or the one entry kept nothing from — so no later pass routes them to the model again. What the distil pass matches on. |
| `sources_gone` | Present and `true` only on a note retired because its raw entries are all gone. Such a record names no `entry_ids` and its title is not handed to routing as an excluded subject — nobody judged the note untrue, so material that comes back is distilled afresh. |

It is not a bin. **It is the mechanism** ("Record retirements so they stick"):
the sources a note was built from still live in the agents' own memory, so
without a record the next aggregation reads the same entry and the next distil
pass re-opens the note the last one removed. The file is therefore part of the
pass's own input, and a lossy round-trip through it is a correctness bug
rather than a cosmetic one.

## What is read, and from where

Reading is confined to the memory paths of **registered and enabled** agents'
own `config_dir`s ("Read only registered and enabled agents' memory", "Confine
reads to registered agents' memory paths"), and is strictly read-only ("Never
write an agent's native memory"). Two readers, written as two readers
("Reintroduce no retired mechanism"):

| Agent | Sources | Ignored |
|---|---|---|
| Claude Code | `<config_dir>/projects/<project>/memory/*.md` — one topic per file, frontmatter carrying its name, description and type | its own `MEMORY.md` roll-up, and `reference`-typed files |
| Codex | `<config_dir>/memories/MEMORY.md` — `# Task Group` sections, each with a recorded cwd and fixed bullet sections — and `<config_dir>/memories/memory_summary.md`, both for the distilled profile and for the **search terms** its `What's in Memory` section states per group | the summary's general-tips roll-up, each group's rollout-reference subsections, and `raw_memories.md` / `rollout_summaries/` entirely ("Read no transcripts or rollouts") |

A reader that cannot parse its source raises with that file's own path; the
pass records one failure naming the agent, the path and the reason, and
everything else completes ("Fail a broken reader loudly and in isolation").

## The distil pass

Two stages, driven by the internal connection ("Distil incrementally in two
stages"), arranged so that **no single request carries the partition's
bodies**:

| Stage | Carries | Returns |
|---|---|---|
| Routing | this round's new raw entries, the partition's **index**, and `RETIRED.md` — no note body at all | one action per entry |
| Writing | one note's body plus the entries routed to it, one request per note actually touched | that note, rewritten |

A partition of a hundred notes that gained three entries therefore costs one
routing request over a hundred index lines and at most three small writing
requests. The routing stage's **output** is confined to four actions per
entry:

| Action | Effect |
|---|---|
| merge | an existing note's body is rewritten to cover the entry; its `origins` gains the entry; `updated_at` moves |
| open | a new note file |
| retire | a note leaves `notes/` and gains a record in `RETIRED.md` |
| keep nothing | no note is written; a `RETIRED.md` record names the entry so no later pass re-routes it; the entry stays in `.raw/` |

Before routing, every pass — the mechanical one included — retires each note
none of whose `origins` is still under `.raw/`, recording it with
`sources_gone` ("Retire a note whose raw entries are all gone"). Aggregation
removes a raw entry when its source stops producing it or files it into
another partition, so this is what keeps a partition's notes derived from
what it actually holds.

With no internal connection configured, no model is called: each raw entry
becomes a note of its own and `MEMORY.md` is written from their frontmatter
("Distil mechanically with no internal connection"). Thinner, not absent.

## Delivery payload

What a session is given ("Deliver the index and the notes path at session
start"), in order:

1. `global`'s index — what is known about the developer.
2. The **whole index** of the current repository's partition.
3. The **absolute path** of that partition's `notes/` directory, and the
   statement that a note's body is read as a file.

It names no tool. A ceiling applies ("Bound delivery and prefer the current
repository"), sized for an index rather than for a handful of lines; when it
binds, the current repository's lines are kept in preference to `global`'s,
the oldest are dropped, and the payload says how many were dropped and which
directory holds them.

## Settings this layer reads

Its two unattended passes are switched and timed from the shared
installation-wide singleton `internal_engine_config` (spec
[internal-engine](../internal-engine/spec.md) carries that row's own description), read
**per pass** rather than at boot so a change takes effect without a daemon
restart:

| Column | Default | Meaning |
|---|---|---|
| `auto_aggregate_enabled` | `true` | Whether the aggregate worker may run. On by default, because a pass only reads the agents' files and only writes derived ones ("Aggregate on an interval and on demand"). |
| `aggregate_interval_s` | `NULL` | `NULL` means the worker's own default, so raising it later reaches every vault that never chose one. |
| `auto_distil_enabled` | `true` | Whether the distil worker may run. Renamed from `auto_organise_enabled` with the pass itself. |
| `distil_interval_s` | `NULL` | As above. |

The one in-flight fact this layer keeps is per-daemon and deliberately does
not outlive it: which partitions are being distilled right now, held in the
shared upkeep-runs registry so a second pass over one partition can be refused
and a surface mounting mid-pass can show the running pass ("Run one distil
pass per partition at a time"). A restart ends the pass and the reading comes
back empty, which is the truth rather than a lost record.

## Delivery state

Per-agent delivery is **one entry in that agent's own settings file** — not a
row here. Coffer's entry is identified by a marker embedded as the argument of
a leading no-op shell command, so detection never depends on `argv[0]`:

| Agent type | File | Event | Guard |
|---|---|---|---|
| Claude Code | `settings.json` | `SessionStart`, matcher `startup\|resume\|clear\|compact` — Claude Code's own matcher vocabulary for that event | none needed |
| Codex | `hooks.json` | `UserPromptSubmit` | once-per-session, keyed on the agent process, since Codex publishes no session id |

The per-agent status answers exactly one question — installed or not — and
carries `agent_uid`, `agent_name`, `installed`, `command` and `event`. It has **no last-fired
timestamp**, on purpose: a fire is an event, not a property, so every fire is
one `memory_delivery_fired` audit row and "has it ever run" is read on the
vault-wide audit surface ("Audit every delivery fire", "Show delivery state on
the agent's own page").

## Audit events

This layer carries no audit surface of its own ("Show memory events on the
vault-wide audit surface"); its events are read on the vault-wide one, which
every kind shares.

| Event | Recorded when |
|---|---|
| `memory_aggregated` | an aggregation pass completes, with the actor distinguishing a scheduled pass from a requested one |
| `memory_distilled` | a distil pass completes, with its merge / open / retire / kept-nothing counts and whether a model was used |
| `memory_delivery_installed` | delivery is installed for an agent |
| `memory_delivery_removed` | delivery is removed for an agent |
| `memory_delivery_fired` | an installed hook fires ("Audit every delivery fire") |

A recall records the usual `mcp_invocations` row and nothing about its query
or its results ("Audit every lifecycle act").
