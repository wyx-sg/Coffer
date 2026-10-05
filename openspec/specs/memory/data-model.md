# Data Model — Memory

The memory layer's state is a directory of Markdown files plus the one
resource file each partition has as a Resource. This document describes
what is on disk, the frontmatter contract, and the handful of records and
values the surfaces answer with. Authority is [`spec.md`](spec.md) and
[Aggregate Agent Memory, Never Write It](../../../docs/decisions/aggregate-agent-memory-never-write-it.md).

## There is no memory table

**This layer adds no table of its own** ("Add no table of its own"). Notes,
raw entries, the index and the retirement record are files; besides them a
partition has only the resource file every Resource has,
`~/.coffer/derived/resources/memory/<name>.json` (the `memory` kind's storage
class is `derived`, spec resource-framework), carrying its name and a
two-field `config` — the repository it was learned in, and nothing else. It is
always enabled.

Everything under `~/.coffer/derived/memory/` is **derived** ("Keep the memory
tree derived and local"), and so are the partitions' resource files: nothing of
it is in the vault repository, and deleting `derived/` is safe. Delete it, run aggregation and distil, and an
**equivalent** set comes back: the same subjects from the same sources, each
note being its raw entry as it stands. What an agent or a person did to the
notes afterwards — a merge, an edit, a retirement mark — is not reproduced.
`.raw/` is the part that *is* byte-reproducible, and it is what a note's
provenance points at.

## On-disk layout

```text
~/.coffer/derived/memory/
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

Four files, four jobs, **one writer each** — which is what makes "Leave the
raw directory to aggregation" checkable by reading the call sites rather than by
trusting a comment:

| Path | Written by | Read by |
|---|---|---|
| `.raw/` | aggregation, and only aggregation | the distil pass only — the file tree leaves it out and its read route refuses it |
| `notes/` | the distil pass, and an agent or person tidying or editing a note | delivery, prompt-time retrieval, the file tree, and any agent holding the path |
| `MEMORY.md` | the distil pass | delivery, and a human opening the folder |
| `RETIRED.md` | the distil pass (including for a note an agent marked retired), and a hand deletion from the web UI | **the next distil pass**, and a human |

- `~/.coffer/derived/memory/` is the root, resolved from `HOME` at every call;
  there is no override. Path construction lives in exactly one module,
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
| `enabled` | not stored: the kind is not toggleable | Always true: the kind declares itself non-toggleable, so every partition is served and enable/disable is refused with `RESOURCE_NOT_TOGGLEABLE` ("Serve every partition to every agent"). |
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
   placement decides on its merits whether it belongs in `global` or
   nowhere. Six of sixteen partitions on the maintainer's live vault were
   dated scratch folders created this way under the previous design.

Partitions are created by aggregation, never by the user and never by an
agent's working directory at read time (see "Provision partitions only from
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

One note is one topic, written by the distil pass from one raw entry, at
`<partition>/notes/<slug>.md`: a YAML frontmatter block, then the entry's body
underneath. An agent that tidies the partition may rewrite or merge it.

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Also the file name. From the title, deduplicated within the partition. |
| `title` | string | The raw entry's title. |
| `description` | string | **One line, written to be read on its own** — it *is* the index entry, and the index is what a session is given ("Store each note as one Markdown file with frontmatter", "Write each index line to stand on its own"). |
| `type` | `user` \| `feedback` \| `project` | As above. |
| `body` | string | The raw entry's body as it stands ("Distil each raw entry into a note mechanically"); an agent that merges notes rewrites it. |
| `partition` | string | `global` or a repository slug. |
| `origins` | list of Origin | Every raw entry this note was built from, and through them every contributing agent ("Store each note as one Markdown file with frontmatter"). A merge appends the merged note's origins to the survivor's ("Teach tidying in the coffer-guide's memory section"). |
| `search_terms` | list of string | Carried up from the entries that supplied them, and restated in the index line so the next agent does not have to guess a word. |
| `created_at` / `updated_at` | string | `updated_at` moves when an agent rewrites the note or a person edits the file in their own editor. |
| `retired` / `replaced_by` | string | Optional. Written by an agent to retire the note: `retired` carries the reason, `replaced_by` the surviving note's slug. The next distil pass records the note in `RETIRED.md`, deletes its file and re-renders the index ("Retire a note an agent marked retired"). |

A note's read carries no fingerprint: the web UI shows a note read-only and no
route saves one (see "Edit a memory in the person's own editor").

There is **no** `status`, no `superseded_by` and no `conflicts_with`. A note
marked `retired` is only transiently in `notes/`: the next distil pass removes
it and records its leaving in `RETIRED.md`. The previous design kept
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

`RETIRED.md` is a list: one record per retired note. A note is retired because
an agent marked it `retired` ("Retire a note an agent marked retired"), because
every raw entry it was built from is gone ("Retire a note whose raw entries are
all gone"), or because a person deleted it by hand ("Delete a memory by
hand"):

| Field | Notes |
|---|---|
| `slug` | The file name the note had under `notes/`. |
| `title` | So the record reads as prose rather than as filenames. |
| `reason` | Why it is no longer true, as the agent that marked it wrote it; `Deleted by hand` on a note a person deleted, whose `entry_ids` are the note's own origin entries so the next distil pass does not recreate it. |
| `replaced_by` | The slug of the note that replaced it, or empty when the subject was simply dropped. |
| `retired_at` | When. |
| `entry_ids` | The raw entries the record accounts for — the retired note's own sources — so no later pass distils them again. What the distil pass matches on. |
| `sources_gone` | Present and `true` only on a note retired because its raw entries are all gone. Such a record names no `entry_ids` — nobody judged the note untrue, so material that comes back is distilled afresh. |

It is not a bin. **It is the mechanism** ("Record retirements so they stick"):
the sources a note was built from still live in the agents' own memory, so
without a record the next aggregation reads the same entry and the next distil
pass re-opens the note the last one removed. The file is therefore part of the
pass's own input, and a lossy round-trip through it is a correctness bug
rather than a cosmetic one.

## What is read, and from where

Reading is confined to the memory paths of **registered and enabled** agents'
own `config_dir`s ("Read only registered agents' memory", "Confine
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

Mechanical, with no model call ("Distil each raw entry into a note
mechanically"). Over a partition the pass does four things, in order:

1. Retires each note none of whose `origins` is still under `.raw/`, recording
   it with `sources_gone` ("Retire a note whose raw entries are all gone").
   Aggregation removes a raw entry when its source stops producing it or files
   it into another partition, so this is what keeps a partition's notes derived
   from what it actually holds.
2. Processes each note whose frontmatter carries `retired:` — a record in
   `RETIRED.md` with the note's origin entry ids, the reason and `replaced_by`,
   the file deleted ("Retire a note an agent marked retired").
3. Turns each raw entry no note and no retirement record accounts for into one
   note as it stands: title, description, type, body, search terms and origin.
4. Renders `MEMORY.md` from the notes' frontmatter.

Merging notes about one subject and judging which statement is stale are the
agent's work, taught by the `coffer-guide` memory section and started from a
partition's Tidy hand-off ("Hand a partition's tidying to the agent").

## Tidy hand-off

Reading one partition carries `tidy_handoff`: a prompt that names the partition,
its absolute directory and the `coffer-guide` section to follow. It is computed
on read from the partition and stored nowhere ("Hand a partition's tidying to
the agent").

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

### A prompt's delivery

For a substantive prompt ("Retrieve the notes a prompt names"): one header line,
then up to three notes of the session's repository partition and `global` that
score at or above the relevance floor and that the session has not been given,
each as `- (<absolute note path>) the user's standing rule is: <title> — <description>`
for a `feedback` note and `… a fact they recorded: …` otherwise. At most 1,500
UTF-8 bytes. The ranking index is held in the daemon's memory and rebuilt when a
partition's `notes/` changes.

## Settings this layer reads

Its two unattended passes are switched and timed from the engine's settings
document, `vault/state/settings/internal-engine.json` (spec
[internal-engine](../internal-engine/spec.md) carries its own description), read
**per pass** rather than at boot so a change takes effect without a daemon
restart:

| Setting | Default | Meaning |
|---|---|---|
| `auto_aggregate_enabled` (`upkeep.aggregate.enabled`) | `true` | Whether the aggregate worker may run. On by default, because a pass only reads the agents' files and only writes derived ones ("Aggregate on an interval and on demand"). |
| `aggregate_interval_s` (`upkeep.aggregate.interval_s`) | `null` | `null` means the worker's own default, so raising it later reaches every vault that never chose one. |
| `auto_distil_enabled` (`upkeep.distil.enabled`) | `true` | Whether the distil worker may run. |
| `distil_interval_s` (`upkeep.distil.interval_s`) | `null` | As above. |

The one in-flight fact this layer keeps is per-daemon and deliberately does
not outlive it: which partitions are being distilled right now, held in the
shared upkeep-runs registry so a second pass over one partition is skipped
rather than started, and a surface mounting mid-pass can show the running pass ("Run one distil
pass per partition at a time"). A restart ends the pass and the reading comes
back empty, which is the truth rather than a lost record.

## Delivery state

Per-agent delivery is **two entries in that agent's own settings file** — not a
record here. Each of Coffer's entries is identified by a marker embedded as the
argument of a leading no-op shell command, so detection never depends on
`argv[0]`, and every entry runs the same command,
`<abs coffer> memory hook --agent-uid <uid> --cwd "$PWD"`, which reads the event
from stdin:

| Event | Matcher | Timeout | Answers with |
|---|---|---|---|
| `SessionStart` | `startup\|resume\|clear\|compact` | 10 s | the bounded index, as `additionalContext` |
| `UserPromptSubmit` | — | 5 s | the prompt's retrieved notes, as `additionalContext` |

| Agent type | File | Approval |
|---|---|---|
| Claude Code | `settings.json` | none; Claude Code runs every hook in its settings |
| Codex | `hooks.json` | Codex runs each entry only once the user has approved it in `/hooks`; Coffer reads every entry's approval from `config.toml`'s `[hooks.state]` without writing it |

The hook is one part — `memory_hook` — of the agent's Coffer connection
(spec agent-registry "Connect an agent to Coffer in one action"), and its state
is reported there as installed or not, with the installed command. It has **no
last-fired timestamp**, on purpose: a fire is an event, not a property, so every
fire is one `memory_delivery_fired` audit row and "has it ever run" is read on
the vault-wide audit surface ("Audit every delivery fire").

### The session ledger

What each session was already given — the notes retrieved for it — is kept per `session_id` in the daemon's
memory, bounded to the 2,048 most recent sessions. It is not written to a file
of its own: at boot it is rebuilt from the last 7 days of `memory_delivery_fired`
audit events ("Remember what a session was given across daemon restarts").

## Audit events

This layer carries no audit surface of its own ("Show memory events on the
vault-wide audit surface"); its events are read on the vault-wide one, which
every kind shares.

| Event | Recorded when |
|---|---|
| `memory_aggregated` | an aggregation pass completes, with the actor distinguishing a scheduled pass from a requested one |
| `memory_distilled` | a distil pass completes — scheduled, or as part of an Update memory action — with the counts of notes written and notes retired |
| `memory_delivery_installed` | the hook is installed for an agent — by connecting it, or by applying its drift item |
| `memory_delivery_removed` | the hook is removed from an agent — by disconnecting it |
| `memory_delivery_fired` | an installed hook fires and delivers — its `details` name the `moment` (`session_start` or `prompt`), the `session_id` and the `notes` it carried; never their text ("Audit every delivery fire") |
| `memory_note_edited` | no longer recorded (the web UI saves no note); the value stays so earlier rows still read |
| `memory_note_deleted` | a person deletes a note by hand in the web UI, naming the partition, the note and the actor ("Delete a memory by hand") |

Prompt-time retrieval (`POST /api/v1/memory/hook`) records one
`memory_delivery_fired` event naming the notes it delivered, and nothing about
the prompt it matched ("Audit every delivery fire").
