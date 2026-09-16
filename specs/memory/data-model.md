# Data Model — Memory

The memory layer's state is a directory of Markdown files plus the one
Resource row each partition already has as a Resource. This document describes
what is on disk, the frontmatter contract, and the handful of rows and values
the surfaces answer with. Authority is [`spec.md`](./spec.md) and
[Aggregate Agent Memory, Never Write It](../../docs/decisions/aggregate-agent-memory-never-write-it.md).

## There is no memory table

**This layer adds no table of its own** (FR-070, SC-002). Facts, digests and
partition metadata are files; the only database presence a partition has is
the row every Resource has, in the kind-agnostic `resources` table, carrying
its name, its `enabled` flag, its per-agent `scope` and a one-field `config`.

Everything under `~/.coffer/memory/` is **derived** (FR-023). Delete it, run
a sync, and the same facts come back — which is what makes it safe to clear
and rewrite a whole partition on any pass that touches it, and why nothing in
it converges with the sync remote.

## On-disk layout

```text
~/.coffer/memory/
├── .source_state.json             # {native_path: last-seen digest} — the skip cache (FR-006)
├── global/                        # facts about the person, delivered wherever they work
│   ├── README.md
│   ├── summary.md                 # the digest organise writes
│   └── facts/
│       └── reply-in-chinese.md
└── coffer/                        # one partition per project, named from its root
    ├── README.md                  # names the absolute project root (FR-011)
    ├── summary.md
    └── facts/
        ├── python-lockfile.md
        └── worktree-development.md
```

- `~/.coffer/memory/` is the root; `$COFFER_MEMORY_ROOT` overrides it for
  tests. Path construction lives in exactly one module,
  `infrastructure/memory/paths.py`, which is also where the traversal guard
  FR-072 asks for lives (`check_segment` refuses an empty, hidden, all-dots
  or otherwise unsafe segment).
- `.source_state.json` is a flat `{native_path: digest}` mapping. Losing it
  costs one pass of unnecessary re-parsing, never correctness — a digest match
  alone never suppresses a rebuild.
- Nothing else lives outside a partition. There is no index file, no journal
  lane and no `.history/`: organise may rewrite a digest freely because memory
  is never the only copy (FR-031).

## Partition

A **partition** is a top-level directory under the memory root *and* one
`memory` Resource. There is exactly one per project plus one named `global`,
and no other partitioning axis exists (FR-010).

| Field | Where it lives | Notes |
|---|---|---|
| `name` | the directory name, and the Resource's name | A readable slug from the project root's own directory name — `/home/dev/coffer` → `coffer`. A collision is resolved by prefixing a parent segment (`work-api` vs `personal-api`), never by an id (FR-011). |
| `project_root` | `Resource.config` (`MemoryPartitionConfig`), restated in the partition's `README.md` | Absolute. Empty for `global`. Persisted on the Resource so a later pass finds the partition by its root rather than reminting a name. |
| `scope` | the Resource's own `scope` column | On creation, the set of agents the partition was aggregated from, so memory flows back to its sources with no setup step. Narrowing or widening it afterwards is the developer's, and a later pass never overwrites it (FR-014). |
| `enabled` | the Resource's own column | The framework's, not this layer's. |
| `fact_count` | counted from `facts/` at call time | Never stored. |

Partitions are created by aggregation, never by the user and never by an
agent's working directory at read time (FR-013) — the `memory` Kind sets
`generic_create_allowed=False`, and `MemoryService.aggregate` opts in
explicitly. Deletion goes through the kind-agnostic Resource route, which
cleans the directory up through the Kind's `on_delete`.

## Fact

One fact is one Markdown file under `<partition>/facts/<slug>.md`: a YAML
frontmatter block, then the source's own words underneath. Round-tripping is
exact — `read_fact(write_fact(f)) == f`, whitespace included — because the
rebuild guarantee depends on it.

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Also the file name. Assigned from the title, deduplicated within the partition. |
| `title` | string | From the source's own heading, name or bullet. |
| `description` | string | One line, from the source when it has one. |
| `type` | `user` \| `feedback` \| `project` | `user` and `feedback` are *personal*: they file into `global` whichever project they came from (FR-012). |
| `body` | string | **The source's own words, never a paraphrase** (FR-021). Summarising happens in the digest. |
| `partition` | string | `global` or a project slug. |
| `origins` | list of Origin | Every place the fact was seen. Two agents contributing the same fact produce one fact with two origins (FR-022). |
| `status` | `active` \| `superseded` | |
| `superseded_by` | fact key, or empty | Set by organise when a later fact contradicts an earlier one. |
| `conflicts_with` | list of fact keys | Organise's finding when it cannot order a disagreeing pair. Nothing settles it by hand (FR-033). |

A fact's **key** is the smallest of its origin keys, so a fact that gains a
second origin on a later pass keeps the identity it had — a merge must not
silently move a `superseded_by` or `conflicts_with` reference off the fact it
was written about.

### Origin

| Field | Notes |
|---|---|
| `agent` | The registered agent's resource name, e.g. `claude-code`. |
| `native_path` | Absolute path of the native file it was read out of. |
| `anchor` | Where inside that file — a heading, a bullet — or empty when the whole file is the fact. Part of the identity, so one file of many facts yields many stable ones. |
| `captured_at` | When Coffer read it. |
| `source_written_at` | When the source says it was written, when it says at all. |

An **origin key** is `sha256(agent \0 native_path \0 anchor)` truncated to 16
hex characters. Hashed rather than concatenated because it travels in file
frontmatter, and an absolute path there leaks the shape of the user's disk
into a place it does not belong.

## What is read, and from where

Reading is confined to the memory paths of **registered and enabled** agents'
own `config_dir`s (FR-001, FR-072), and is strictly read-only (FR-002). Two
readers, written as two readers (FR-073):

| Agent | Sources | Ignored |
|---|---|---|
| Claude Code | `<config_dir>/projects/<project>/memory/*.md` — one fact per file, frontmatter carrying its name, description and type | its own `MEMORY.md` roll-up, and `reference`-typed files |
| Codex | `<config_dir>/memories/MEMORY.md` — `# Task Group` sections, each with a recorded cwd and fixed bullet sections — and `<config_dir>/memories/memory_summary.md`, the distilled profile | the summary's general-tips roll-up, each group's rollout-reference subsections, and `raw_memories.md` / `rollout_summaries/` entirely (FR-003) |

A reader that cannot parse its source raises with that file's own path; the
pass records one failure naming the agent, the path and the reason, and
everything else completes (FR-005).

## Derived files a partition holds

| File | Written by | Contents |
|---|---|---|
| `README.md` | aggregation | What the partition is and the absolute project root it was minted for, so the directory explains itself to a human browsing it. |
| `summary.md` | organise | The partition's digest — one line per **active** fact, superseded ones omitted, grouped by type (project first, then the two personal types) and newest first within a type by the fact's latest origin timestamp. Rewritten freely, with no prior revision archived (FR-031). With no internal connection configured it is still produced, mechanically: facts grouped by type, newest first, one line each from their frontmatter (FR-032). |

## Settings this layer reads

Its two unattended passes are switched and timed from the shared
installation-wide singleton `internal_engine_config` (spec
[vault-sync](../vault-sync/spec.md) carries that row's own description), read
**per pass** rather than at boot so a change takes effect without a daemon
restart:

| Column | Default | Meaning |
|---|---|---|
| `auto_aggregate_enabled` | `true` | Whether the aggregate worker may run. On by default, because a pass only reads the agents' files and only writes derived ones (FR-007). |
| `aggregate_interval_s` | `NULL` | `NULL` means the worker's own default, so raising it later reaches every vault that never chose one. |
| `auto_organise_enabled` | `true` | Whether the organise worker may run. |
| `organise_interval_s` | `NULL` | As above. |

The one in-flight fact this layer keeps is per-daemon and deliberately does
not outlive it: which partitions are being organised right now, held in the
shared upkeep-runs registry so a second pass over one partition can be refused
and a surface mounting mid-pass can show the running pass (FR-066). A restart
ends the pass and the reading comes back empty, which is the truth rather than
a lost record.

## Delivery state

Per-agent delivery is **one entry in that agent's own settings file** — not a
row here. Coffer's entry is identified by a marker embedded as the argument of
a leading no-op shell command, so detection never depends on `argv[0]`:

| Agent type | File | Event | Guard |
|---|---|---|---|
| Claude Code | `settings.json` | `SessionStart`, matcher `startup\|resume\|clear\|compact` — Claude Code's own matcher vocabulary for that event | none needed |
| Codex | `hooks.json` | `UserPromptSubmit` | once-per-session, keyed on the agent process, since Codex publishes no session id |

The per-agent status answers exactly one question — installed or not — and
carries `agent`, `installed`, `command` and `event`. It has **no last-fired
timestamp**, on purpose: a fire is an event, not a property, so every fire is
one `memory_delivery_fired` audit row and "has it ever run" is read on the
vault-wide audit surface (FR-055, FR-064).

## Audit events

This layer carries no audit surface of its own (FR-065); its events are read
on the vault-wide one, which every kind shares.

| Event | Recorded when |
|---|---|
| `memory_aggregated` | a sync pass completes, with the actor distinguishing a scheduled pass from a requested one |
| `memory_organised` | an organise pass completes, with its merge / supersession / conflict counts and whether a model was used |
| `memory_delivery_installed` | delivery is installed for an agent |
| `memory_delivery_removed` | delivery is removed for an agent |
| `memory_delivery_fired` | an installed hook fires (FR-055) |

A recall records the usual `mcp_invocations` row and nothing about its query or
its results (FR-063).
