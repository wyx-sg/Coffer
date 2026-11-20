# Keep Memory in One Place in the Vault, Written by the Agents Themselves

**Status**: Accepted
**Date**: 2026-11-19
**Deciders**: Yuxing Wu
**Related**: [Tidying Knowledge Is the Agent's Job, One Hand-Off Recorded as One Change](tidying-knowledge-is-the-agents-job.md), [Knowledge Is Plain Files](knowledge-is-plain-files.md), [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md), [Automation Is a Scheduled Prompt](automation-is-a-scheduled-prompt.md), design principle [Pull, not push](../../docs-site/architecture/design-principles.md#pull-not-push), research note [agent memory](../research/agent-memory.md), spec memory "Keep memory in one place in the vault", spec memory "Hand a session its project's memories at start"

## Context

Until this decision Coffer synced memory in both directions. It read Claude
Code's auto memory and Codex's memories into a hub in the vault, one file per
memory, and wrote the hub back into each agent's own memory: a marked block in
Claude Code's `MEMORY.md` plus `coffer_*.md` files, and an `extensions/coffer/`
folder in Codex. Around that sat an echo filter (a memory copied into an agent
must not be read back as new), a ledger of the copies, a preview of a first or
large sync, a one-click undo, a timer with its own switch and interval, a
follower for every Codex version folder, and a `memory_reader` facet per agent.

Three things went wrong with it.

- **Only two agents could take part.** Every other agent Coffer supports or is
  adding (Cursor, OpenCode, Antigravity, DeepSeek's CLI) has no native memory
  Coffer can read and write, or one whose format is undocumented. Each new
  agent would need its own reader and writer, and Cursor shows the risk: it
  shipped memories and removed them within five months.
- **Most of what it moved was noise.** On the owner's Mac on 2026-11-11 the
  hub held 437 entries; about 70% were Codex's per-task log bullets ("Batch 7
  TH created 120, 0 failed"), copied because the agent wrote them.
- **It was the most complex part of Coffer** for what it delivered: the echo
  filter, the ledger, the preview and the undo existed only because Coffer
  wrote into files it did not own.

The owner asked for one scheme for every agent, central reads and writes, and
no multi-way sync (2026-11-19), and asked how claude-mem does it.

How comparable products handle memory (research note
[agent memory](../research/agent-memory.md), checked 2026-09-24 and again
2026-11-19):

- **claude-mem** (the most-starred memory add-on) captures every tool call
  through Claude Code hooks, has a model compress them into observations in its
  own SQLite database, and at `SessionStart` injects an index of recent
  observations, with search tools for the detail. It owns its store and never
  syncs into the agent's own memory.
- **Claude Code** auto memory is Markdown topic files with typed frontmatter
  plus a one-line-per-entry `MEMORY.md` index loaded at session start (200
  lines or 25 KB); the agent writes it in-loop with its own file tools.
- **Codex** distils memories from finished sessions in the background and loads
  a 2,500-token summary; a sandboxed sub-agent consolidates the folder, which
  is under git.
- **Letta Code** keeps memory as files in a git repository that the agent edits
  itself; a "dreaming" sub-agent consolidates them.
- **agentmemory** and **Cognee** inject a budgeted block through a
  `SessionStart` or per-prompt hook.
- The third parties inject; they rarely write the agent's own files. The one
  that did (claude-subconscious writing into `CLAUDE.md`) backed it out.

The field converged on three things: Markdown files as the source of truth,
the working agent writing them itself, and a compact text pushed at session
start with the rest read on demand.

## Options Considered

### M1 — Keep syncing into each agent's own memory

Read Claude Code's and Codex's memory into the hub and write the hub back into
each.

- **Pros.** Already built and in use. Each agent loads the shared memories the
  way it loads its own, with no hook.
- **Cons.** Works for two agents only, and every further agent needs a reader
  and a writer for a format that changes without notice. It copies whatever an
  agent writes, noise included. The echo filter, the copy ledger, the preview
  and the undo exist only to make writing into someone else's files safe.
- **Why it loses.** It cannot be the one scheme for every agent the owner asked
  for, and it is the most complex part of Coffer.

### M2 — Do what claude-mem does

Capture every tool call through hooks, compress with a model, store in a
database, inject at session start, and offer search tools.

- **Pros.** Independent of any agent's memory; every agent with hooks is
  treated the same. High recall.
- **Cons.** One model call per session or per batch of tool calls, paid by the
  person. Coffer becomes a memory system with a database and a compressor,
  which is exactly what Coffer's lean principle says the agent can do itself.
  Unbounded capture with no retirement is the pattern the research note lists
  under "worth avoiding". It also duplicates every agent's own memory.
- **Why it loses.** It adds the most machinery and model cost of any option.

### M3 — One hub of Markdown files the agents write themselves, handed over by a session-start hook (chosen)

The hub is `vault/memory/projects/<project>/`, one folder per project, one
file per topic. The agent writes it with its own file tools, following rules
in the `coffer-guide` skill. Coffer reads and writes no agent's memory. One
`SessionStart` hook per agent runs `coffer memory session-start`, which prints
the project's memories, up to 4 KB, and the path and title of each file that
does not fit. Coffer's own chat, channel and scheduled turns put the same text
in the system prompt, and set `COFFER_MEMORY_IN_PROMPT=1` so the hook stays
silent in them. A Tidy hand-off has the person's own agent merge and split
topics, committed as one undoable change; a periodic tidy is a scheduled task
the person creates from the Memory page.

- **Pros.** One mechanism for every agent that has a session-start hook, and
  for Coffer's own turns without one. The files sync like any other vault file,
  so memory follows the person across machines. Nothing Coffer writes lands in
  a file it does not own except one hook entry, which it adds beside the
  agent's own hooks and removes alone. The echo filter, the ledger, the preview,
  the undo, the timer, the per-agent readers and writers and the `memory_reader`
  facet all go.
- **Cons.** Memory depends on the agent choosing to write it, guided only by
  the skill's rules. An agent's own memory keeps running beside the hub; turning
  it off is the person's choice. An agent with no session-start hook (or no
  hook support) is handed memories only in Coffer's own turns. Codex asks the
  person to review a new hook once. Writing to the hub is a write outside the
  repository, which an agent's sandbox or permission settings may need to allow.
- **Why it wins.** It is the shape the field converged on, it is the only
  option that treats every agent the same, and it is the smallest.

### M4 — Pure MCP: memory tools to save and search

The agent calls `memory_save` and `memory_search` tools on Coffer's MCP
gateway.

- **Pros.** The simplest delivery to build; works in every agent with MCP.
- **Cons.** Nothing reaches a session unless the agent decides to call the
  tool. Coffer measured exactly this with knowledge: agents did not reach for a
  retrieval tool they had to remember to call (five trials), while they read
  files constantly ([Knowledge Is Plain Files](knowledge-is-plain-files.md)).
  A save tool is also a second way to do what the agent's own file tools
  already do.
- **Why it loses.** Preferences such as "answer in Chinese" are needed in every
  turn, and pull alone does not deliver them.

### M5 — One hub, delivered by writing into each agent's instruction file

Keep the hub, but render it into a marked block of `~/.claude/rules/`,
`AGENTS.md` and so on instead of running a hook.

- **Pros.** No hook and no trust review; the agent loads its instruction file
  natively.
- **Cons.** Coffer again writes into files the person and the agent also edit,
  needing markers, backups and a rewrite on every hub change and every machine.
  Instruction files are global or per repository, not per project key, so a
  project's memories end up either in every session or inside the repository's
  own files. Each agent's instruction-file location differs and moves (Windsurf
  moved `.windsurf/` to `.devin/`).
- **Why it loses.** It brings back the writing-into-others'-files problem M3
  removes, for every agent separately.

## Choices inside M3

- **One topic per file, one memory per line.** A file per memory (the earlier
  hub, and Claude Code's own layout) made related memories hard to read
  together and made the 4 KB cap a list of single lines. Memories used together
  belong in one file (the owner, 2026-11-19). An agent first looks for a
  fitting topic file and appends; a tidy merges and splits topics.
- **The format and rules are Coffer's, not the person's.** Knowledge
  collections let the person write each collection's rules, because a
  collection's shape follows its subject. Memory has one shape, and the hook,
  the cap and the Memory page all read it, so the frontmatter (`title`, `type`
  of `user`/`feedback`/`project`, `updated`) and the rules are fixed and stated
  in `coffer-guide` (the owner, 2026-11-19).
- **Coffer names format problems and does not fix them.** A file missing a
  field or with an over-long line is still read and shown with its problems;
  fixing it is the agent's work, usually in a tidy.
- **Memory is about the person; knowledge is about the world.** What the
  person is like, how they want an agent to work and a project's state the
  repository does not record go in memory. Facts about an outside system, a
  procedure or a reference go in a knowledge collection, read on demand. The
  rule is stated in `coffer-guide`, and a tidy moves what landed on the wrong
  side.
- **No built-in timer for tidying.** A periodic tidy is a scheduled task like
  any other ([Automation Is a Scheduled Prompt](automation-is-a-scheduled-prompt.md)).

## Decision

M3. Coffer keeps memory as Markdown topic files in
`vault/memory/projects/<project>/`, and the agents read and write them with
their own file tools under rules fixed in `coffer-guide`. Coffer reads and
writes no agent's native memory. While the memory feature is on, each
registered agent carries one `SessionStart` hook of Coffer's; Coffer's own
turns carry the same text in the system prompt. A tidy is one hand-off and one
commit. On upgrade Coffer removes what an older build wrote into the agents and
rewrites the older hub entries as topic files.

This reverses two earlier rules: the hub is no longer synced into each agent's
own memory, and Coffer now installs one hook into each agent. The hook is
justified where "Pull, not push" ruled hooks out because memory is the one
thing needed in every turn and pulled by nobody; it stays within a fixed 4 KB.

## Consequences

- **Two machines editing the same topic file can conflict.** The hub syncs as
  vault files, and two agents on two machines appending to one topic before a
  sync round produce a git merge. For one person this is rare, and appended
  lines usually merge automatically; a real conflict goes through vault sync's
  ordinary conflict handling.
- **A new agent takes part by declaring where its hook goes** (the descriptor's
  `session_hook`) and nothing else. An agent with no hooks is handed memories
  only in Coffer's own turns.
- **Writes outside the repository need allowing.** The guide and docs say how:
  an `Edit(<hub>/**)` rule under Claude Code's `permissions.allow`, and Codex's
  `writable_roots` under `[sandbox_workspace_write]`.
- **Whether to turn an agent's own memory off is the person's choice.** Coffer
  does not change it; the docs say how.
- **Codex reviews the hook once** before running it (`/hooks`, or Settings >
  Hooks in the app).
- Enforced in `backend/coffer/domain/memory/` (format and context),
  `backend/coffer/application/memory/hook_target.py` (the hook reconciler) and
  `backend/coffer/infrastructure/memory/legacy.py` (the upgrade cleanup), and in
  spec [memory](../../openspec/specs/memory/spec.md).
