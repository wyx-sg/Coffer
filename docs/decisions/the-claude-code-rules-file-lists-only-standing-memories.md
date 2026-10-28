# The Claude Code Rules File Lists Only Standing Memories and Names the Task Topics

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Yuxing Wu
**Related**: [Global Memories Live in a Claude Code Project of Their Own, Pointed at From a Rules File](global-memories-in-claude-code-live-in-a-global-project.md), [File a Memory Where Its Agent Filed It](file-a-memory-where-its-agent-filed-it.md), [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), research note [agent memory](../research/agent-memory.md), spec memory "Write global memories into a Claude Code global project and point at them from a rules file"

## Context

`~/.claude/rules/coffer-memory.md` is loaded into every Claude Code session. It
followed its design (one line per `global` memory, no text), bounded at 25 KB
on the assumption that global memories would be few. Once a memory is filed
where its agent filed it, every Codex app chat outside a repository yields
global memories. On the maintainer's Mac on 2026-10-28 the file held 74 lines,
all from Codex: 23.8 KB, about 6k tokens. Each line was about 300 characters, of
which about 118 were the copy's absolute path; the description was cut at 200
characters. 27 lines came from Codex's `memory_summary.md` (the profile and
the preferences that hold whatever the task). 47 came from `MEMORY.md` task
groups. Those were specific to one job (an IA sheet, a PIC notice, an
appraisal), and about a dozen restated a summary preference, because Codex
lifts a group's preference into its summary.

The same check found that in 14 days, none of 180 Claude Code sessions opened
a `coffer_*.md` file. What reaches a session is the text of the lines it
loads, not the files behind them.

Comparable products:

- **Codex** splits the same way. `memory_summary.md` is injected and truncated
  to 2,500 tokens; `MEMORY.md` is grepped by keyword when a task calls for it.
- **Claude Code** loads the first 200 lines of a project's `MEMORY.md` and
  reads topic files on demand.
- **Windsurf** caps always-on global rules at 6,000 characters.
- **Cursor** and Windsurf's `model_decision` rules keep only a description
  always visible.
- **agentmemory** and **claude-mem** inject a bounded index of about 2,000
  tokens at session start.

## Options Considered

### Option 1 — Keep one line per memory, bounded at 25 KB

- **Pros.** Nothing changes.
- **Cons.** About 6k tokens in every session, most of it irrelevant to the
  session, and growing toward the cap.

### Option 2 — Shorter lines and a lower bound, newest first

Write the folder once and give each line its title and file name only, under
6 KB.

- **Pros.** Small change, about 1.5k tokens.
- **Cons.** The cut is by age, not by kind. An old standing preference (the
  person's profile among them) falls off while a newer one-off task note stays.
  Ordering by relevance or by last use is not possible: the file is written
  before any task is known, and Claude Code does not report what it read.

### Option 3 — Deduplicate before listing

- **Pros.** Removes the restatements.
- **Cons.** Only exact repeats can be found mechanically; the restatements are
  paraphrases. Merging them is curation, which belongs to the agents, not to
  Coffer. It saves about a fifth, far from the target.

### Option 4 — Scope by project or working directory

- **Pros.** Each session sees less.
- **Cons.** These memories belong to no project, so it saves nothing without
  reversing *File a Memory Where Its Agent Filed It*. Claude Code's
  path-scoped rules match files, not the working directory.

### Option 5 — Two layers, as Codex keeps them (chosen)

The rules file lists the **standing** memories: everything except a Codex
task-group bullet, with Codex's User Profile first. Each gets one line of at
most 120 characters of title and description, plus its file name; the folder is
written once. The task-group memories are not listed. One line names their
groups with a count each, and points at the global folder's `MEMORY.md`, whose
Coffer block lists every memory under its group, uncapped (no session loads that
file by itself). The rules file is bounded at 8 KB, standing lines newest first
after the profile, and the line naming the groups at 2 KB.

- **Pros.** About 1–1.5k tokens on today's data. The standing preferences and
  the profile stay in every session, as text, which is the only form the check
  showed being used. It is Codex's own split, read from where Codex put each
  memory, so Coffer judges nothing. The restatements go with the group bullets.
- **Cons.** A task memory reaches a session only if the model sees its topic,
  opens the index, then the file. Given the reading figures above, that will
  be rare. The group is read from the Codex identity string
  (`<file>::<group>::<heading>::<digest>`), so a change to how the reader builds
  identities has to keep `codex_identity` in step. The topic names are Codex's
  group titles, which can be long; they are cut at 60 characters.

## Decision

Option 5. A memory from Claude Code on another machine has no task group, so
it stays standing; when such memories grow, the 8 KB bound and the "more,
listed in `MEMORY.md`" line apply to them as well.

## Consequences

- The rules file shrinks from about 6k tokens to about 1–1.5k on the
  maintainer's data, and stays under 8 KB.
- The global folder's `MEMORY.md` block is grouped and uncapped; project
  folders keep their 30-line block.
- Writing into Codex Desktop's newer `memories_v2/` folder, and the profile
  echoing Claude Code memories that Codex restated without the `[via Coffer]`
  tag, are separate problems found by the same check and are not decided here.
