# Follow Codex's Memory Into Every Version Folder It Keeps

**Status**: Accepted
**Date**: 2026-11-03
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [File a Memory Where Its Agent Filed It](file-a-memory-where-its-agent-filed-it.md), [Claude Code Reads Other Agents' Memories as Text It Loads](claude-code-reads-other-agents-memories-as-text.md), [A Codex Memory Is Identified by Its Content, and a Rewrite Keeps the Identity](codex-memory-identity-is-content-with-rewrite-carry-over.md), spec memory "Write the hub into Codex's memory extension", "Read Codex's v2 memory", "Read no transcripts or rollouts"

## Context

Codex now keeps two memory folders side by side in its config directory:
`memories/` (v1) and `memories_v2/` (v2). The source (openai/codex
`codex-rs/protocol/src/memory_version.rs`, `codex-rs/core/src/config/mod.rs`,
main at 2026-11-03) says the folders are separate so v1 cleanup and rollback
stay independent of v2. `config.toml` can choose with `[memories] version` and
`dual_write`. With neither set, a profile without `memories/` gets v2 and an
existing one keeps v1.

Codex Desktop does not go by `config.toml`. On the maintainer's Mac on
2026-11-03 (Desktop 26.1027, CLI 0.166), the app decides per thread. It reads
two server-side switches and asks its app server whether v2 is ready (at least
20 consolidated threads). It then passes `-c memories.version=<v1|v2>` and
`-c memories.dual_write=…` (default on) when it starts each thread.
`config.toml` held only `[features] memories = true`. Both folders were
updated that day: v1's `MEMORY.md` at 16:32 and v2's `memory_summary.md` at
17:36. Coffer wrote only into `memories/extensions/coffer/` and read only
`memories/`. v1 held 70 Coffer resources and v2 held none, so a v2 thread saw
nothing that Claude Code had learned.

The two versions differ:

- **Extensions are the same.** v2 reads
  `memories_v2/extensions/<name>/instructions.md` and `resources/*.md`, treats
  a deleted resource as a signal to forget, and prunes only resources whose
  names start with a timestamp (after 14 days).
- **The consolidated memory is not.** v2 has no `MEMORY.md`, no task groups and
  no `applies_to: cwd=`. Its only output is `memory_summary.md`, which is
  injected into every session and capped at about 10 KB. It has User Profile,
  User preferences, General Tips and What's in Memory. What's in Memory files
  each piece of work under `### <project scope>` / `#### <date>`, with a scope
  named in words ("Account Jira delivery"). Each piece is one sentence that
  points at `rollout_summaries/<file>`. That file opens with a four-line header
  (`thread_id`, `updated_at`, `rollout_path`, `cwd`), and the header is the
  only place the directory is recorded.

How comparable code handles two versions:

- **Codex's own import from Claude Code** (`codex-rs/external-agent-migration/src/memory_import.rs`)
  writes into both folders when `memories/` exists and only into v2 otherwise.
  It takes both folders' locks before it touches either.
- **Codex's startup pipeline** runs both versions while `dual_write` is on and
  v1 is selected, and runs v2 alone after cutover.

## Decision

1. **Write into every memory folder that is there.** Each folder is its own
   write location, with its own ledger key, status and copy counts. The v1
   folder keeps the key copies were filed under before. A `memories_v<N>` that
   Coffer does not know is listed as a location that writes nothing, and the
   Memory page reports it as unrecognised with its path.
2. **Read both versions.** v1 is read as before. From v2's summary the reader
   takes the profile, each preference, each General Tips paragraph and each
   What's in Memory topic. A topic is filed under the `cwd:` in the header of
   the rollout summary it points at. Nothing below that header is read. A topic
   with no pointer, or a header without a `cwd:`, is global. A topic's identity
   names its scope, so `codex_identity.task_group()` returns that scope the
   same way it returns a v1 task group. The topic then reads as task material,
   not as a standing memory.
3. **v2 owns the profile while it is there.** With a v2 summary present, v1's
   summary yields no profile, and none of the preferences v2 states word for
   word.

## Options

### Where to write

**A. Every folder that is there (chosen).**
This is the rule Codex's own import uses. It does not have to guess which
version a thread will read, and on this Mac that is a per-thread server
decision Coffer cannot see. A new version only needs its folder name added.
Cost: Codex consolidates the same resources twice, once per version, as its
own dual write already does. After cutover, the v1 copies keep being written
for a folder nobody reads. That is harmless, and it stops once the person
deletes `memories/`.

**B. Follow the version Codex selects.** Parse `[memories] version` and
`dual_write`, plus the "fresh profile gets v2" rule, and write one folder.
Fewer files. But Desktop does not choose through `config.toml`, and that is
exactly how this bug happened: the config says nothing while Desktop reads v2.
The rule also lives in Codex's code and changes with it.

**C. Only v2.** The smallest change. But CLI sessions on an existing profile
still default to v1, and they would stop getting memories.

### How to read v2's project work

**R2. Read the summary, and take the directory from the pointed-at summary's
header (chosen).** The topics are the only project knowledge v2 keeps. The
header line is metadata, the same kind of exception the Claude Code reader
already makes for a transcript's recorded `cwd`. It files a topic under the
same rule as a v1 group (inside a repository → that project, otherwise
global).

**R1. Keep reading only v1.** No code. But once Codex cuts over, v1 stops
changing, and nothing Codex learns reaches the hub again.

**R3. Read the rollout summaries themselves.** That gives the most detail, but
they are per-session task history. Reading them would break "Read no
transcripts or rollouts", and the material is already distilled into the topic
line.

**Route by scope name instead of the header.** A scope is a name Codex chose
("Account operations and investigations"), not a path. Mapping names to
repositories is a guess, and a wrong filing is worse than a global one.

### Overlap while Codex dual-writes

While both versions are live, one piece of work can arrive twice: as v1
task-group bullets, and as a v2 topic sentence. Options:

- **Accept it (chosen).** The two are different text. Coffer does no
  content-level dedup (principle F: Coffer does mechanical work only), and the
  agents' own curation can merge them.
- **Read v2 topics only once v1 goes stale** (no change for N days). This
  flips once at cutover. When it does, every v1 entry is unpublished and its
  copies removed, which replaces rich bullets with one-line pointers. It also
  hangs on a threshold that has no right value.
- **Read only v2 while it is there.** v2 summaries are capped at 10 KB, so
  most of v1's knowledge would disappear from the hub the day v2 appears.

Only the profile and preferences are deduplicated. Both versions write them
from the same evidence, and two profiles would both be pinned in every Claude
Code session.

## Consequences

- On first install, Coffer writes one copy per hub entry into `memories_v2/`
  (about 70 on the maintainer's Mac). That is past the preview threshold, so
  the Memory page asks for one confirm.
- The Memory page and the agent's Memory tab list Codex's folders one by one.
  When Codex adds a version Coffer does not know, the "needs you" strip shows
  it.
- The preview counts a copy once per folder, so Codex's write count is about
  double the number of memories while both folders exist.
- Once the person deletes `memories/`, the next sync stops writing it. Undo
  forgets that folder's ledger rows.
