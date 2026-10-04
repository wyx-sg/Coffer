# Memory Reaches a Session at Two Moments: an Index at Start and the Notes a Prompt Names

**Status**: Accepted
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md), [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md), [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), [principles](../../docs-site/architecture/principles.md) (Persistence), design principle [Pull, not push](../../docs-site/architecture/design-principles.md#pull-not-push), research note [agent memory](../research/agent-memory.md), spec memory "Deliver the index and the notes path at session start", spec memory "Retrieve the notes a prompt names", spec memory "Bound delivery and prefer the current repository", spec memory "Deliver to channel turns through the system prompt", spec memory "Install delivery hooks explicitly and removably", spec memory "Audit every delivery fire", spec memory "Expose no memory tool and name the memory root at session start", spec memory "Keep the memory tree derived and local"

## Context

Coffer's memory layer reads what Claude Code and Codex learned, distils it into
notes of its own, and hands them back
([Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md)).
The first design handed back one thing: the **whole index at session start**,
through a hook the user installs per agent, with nothing reaching a session
after its first moment. This ADR decides when memory reaches a session, and on
what evidence; the design principle
[Pull, not push](../../docs-site/architecture/design-principles.md#pull-not-push)
is the frame it works inside (every delivery goes through an installed,
removable, audited hook).

The evidence is an eval set built on 2026-09-29 from the maintainer's real
transcripts (read only; 131 Claude Code sessions, 225 canonical Codex
sessions): **107 hand-checked moments** where an agent needed a fact, rule or
known trap that some store held, 78 of them held *before* the moment. It was
used three ways.

**Baseline.** Over the 78 held needs, the right information reached context in
65% and the agent **used it in 31%**. Almost all of what reached context came
through Claude Code's own native `MEMORY.md`, not Coffer: Coffer's delivery
accounts for well under 10% of the successes, and for Codex it delivered
nothing. The held failures split in half: **27 were in context and not acted
on** (the Node 20 rule for `make verify` read and then broken in four sessions;
worktree cleanup declined as "unasked" five times), and **27 were never
delivered** (the index truncated, the wrong partition, or an agent Coffer never
reached). 45 of the 107 were a known trap repeated — the largest category.

**Offline replay** of every case against today's store, using the real prompts
and commands before each moment:

| Mechanism | Held needs delivered (80) | Held failures delivered (56) | Noise, tokens per session (Claude / Codex) |
| --- | --- | --- | --- |
| Session-start index as shipped | 4% | 4% | 456 / 0 |
| Session-start index capped at 1.8 KB, partition resolution fixed | 18–22% | 21–23% | ~420 / ~395 |
| Whole index, untruncated | 76% | 75% | 6,864 / 2,431 |
| Prompt-time BM25, k=5 | 35% (Codex 64%, Claude 19%) | 43% (56% of the never-delivered) | 4,157 / 1,871 |
| Prompt-time embeddings (e5-large), k=5 | 36% | 46% | 4,595 / 2,222 |
| Command-time triggers derived by rule, broad | 42% | 46% | 3,667 / 511 |
| Command-time triggers derived by rule, pruned | 18% | 21% | 544 / 209 |

Prompt-time retrieval was the only fix for "never delivered"; command-time
matching was the only thing that reached "in context but not acted on" and the
traps. Triggers derived automatically were either noisy (about 25 notes fired
per session, 0.8 of them relevant) or, once pruned, dropped the very commands
the traps live on (`make verify`, `gh pr merge`, `sed`).

**Live mechanics** (Claude Code 2.1.281, Codex 0.155.1):

- Claude Code keeps a hook's output inline only up to ~10,000 characters, for
  every event and both output formats; past that the model sees a ~2 KB
  preview. Coffer's index was 30–45 KB, so the model saw the newest six
  `global` lines. The cap is 9,500 UTF-8 bytes (`DELIVERY_CEILING_BYTES` in `domain/memory/delivery.py`).
- Claude Code's `PreToolUse` `additionalContext` arrives **after** the command
  has run, with its result: a reminder there can fix recovery, never the first
  attempt. Only `permissionDecision: "deny"` stops the first attempt.
- Codex runs all four hooks (`SessionStart`, `UserPromptSubmit`,
  `PreToolUse`, `PostToolUse`) and delivers JSON
  `hookSpecificOutput.additionalContext` from each; plain stdout is ignored on
  the tool events; past ~2,500 tokens it cuts the middle; an untrusted hook is
  skipped silently. It honours `deny` and shows the model "Command blocked by
  PreToolUse hook: <reason>". Coffer's Codex hook had never run at all — never
  trusted, `coffer` not on the hook's `PATH`, a once-per-session guard keyed on
  `$PPID` — and has since been fixed.

**Live compliance**, Claude Code on sonnet, six scenarios where the trap bit
(Node 20 before `make verify`, cleanup after `gh pr merge`, Coffer's MCP for
Jira instead of `skynet-base jira`, BSD `sed \b`, missing GNU `timeout`,
`COFFER_CORS_ORIGINS` for e2e on a spare port), three runs per cell, 72 runs:

| Condition | Mistake avoided on the first attempt | Avoided by the end | Injected tokens per run |
| --- | --- | --- | --- |
| Session-start index as shipped | **1 / 18** | 9 / 18 | 11.2k emitted, ~500 visible |
| Prompt-time BM25, k=3, ≤1.5 KB, score floor | 15 / 18 | 15 / 18 | 276 |
| Command-time guard: deny the matching command once, the note as the reason | 18 / 18 | 18 / 18 | 72 |
| **Both** | **18 / 18** | **18 / 18** | 321 |

First attempt, both against today: one-sided Fisher exact p ≈ 2×10⁻⁹. The
combination also took fewer turns (4.5 against 5.3) and needed fewer blocks
than the guard alone (0.39 against 0.89 per run), because a rule retrieved at
the prompt got the first command right. Retrieval's only miss was Node 20:
"run make verify" shares no word with the vitest note, and the guard caught it.
Two findings about wording: in an earlier round an imperative note ("delete the
branch and the worktree") delivered at `PreToolUse` was quoted back to the user
as prompt injection; worded as "the user's standing rule is …", 0 of 72 runs
flagged a note. And one control failed under every condition: "reply in
Chinese" is a rule about every turn, which no retrieval or trigger addresses.

The limits of the evidence: Claude Code on sonnet only; single-prompt
sandboxes; triggers hand-written for exactly these six traps, so the guard's
18/18 is a ceiling for authored triggers. Codex compliance runs are still
outstanding (the only Codex provider on the machine refused every call); the
Codex delivery path is verified against a fake model, including `deny`.


**What the guard measured, and what use showed.** The command-time guard was
the strongest mechanism in the eval, and it was tried in the product: a person could attach a
**trigger** to a note (a command or error pattern), and the first matching
command in a session was denied once with the note as the reason. In use it
never operated. Over thirty days on the maintainer's machine memory was
delivered **414 times, a command was held zero times, and no trigger was ever
armed**. Four triggers existed, all proposed by the distil pass; the web UI
had no place to arm one, so nothing a person could reach turned a proposal
into a guard. One of the four matched browser tool names against shell
commands, where it could never match what it meant. The 18/18 above is a
ceiling for hand-written triggers, and the only hand there was the
experiment's. A mechanism that depends on authoring nobody does delivers
nothing, which is the same finding as `coffer__recall`'s five calls (Option G).

## Options Considered

### Option A — Two moments: a bounded index at start and lexical retrieval per prompt (chosen)

1. **Session start: the bounded index.** `global`'s index and the
   current repository's, repository lines preferred, at most 9,500 UTF-8
   bytes, naming the memory root and the notes directory. It covers the rules a
   user would otherwise restate in the first message.
2. **Each prompt: lexical retrieval.** A `UserPromptSubmit` hook asks the
   daemon to rank every partition's notes — title, description, search terms
   and body — against the prompt with BM25 (CJK text as bigrams), and injects
   the top **k = 3** (`TOP_K` in `domain/memory/retrieval.py`) as each note's index
   line and path, at most **1.5 KB** (`RETRIEVAL_CEILING_BYTES`),
   only above a **relevance floor**. Prompts under three words ("continue",
   "继续") trigger nothing, and a note already injected in the session is not
   injected again. The ranking index is held in memory, rebuilt from the note
   files when they change, and is derived state; nothing chunks or embeds the
   notes.
3. **Wording.** Every injected note reads as provenance plus fact: "Coffer
   memory, a note the user wrote (`<file>`): the user's standing rule is: …".
   Nothing delivered instructs a destructive step; a rule that authorises an
   action is delivered at the prompt, where the user's own words came first.
4. **Per-turn rules are not memory's job.** A rule about every reply — its
   language, its tone — belongs in the instructions the agent loads on every
   turn (`CLAUDE.md`, `AGENTS.md`), which the user owns and Coffer does not
   write, as it does not write the agent's memory.
5. **Both agents, same payloads.** Claude Code and Codex get the same two
   events through JSON `additionalContext` — `SessionStart` and
   `UserPromptSubmit` — installed with the absolute path of the `coffer`
   binary, guarded once per session on the hook's `session_id`, every payload
   under both agents' cut-offs. An untrusted Codex hook is reported as
   untrusted, not as installed. A channel-driven turn gets the index and the
   per-prompt retrieval through the system-prompt append the turn platform
   already composes.
6. **Fail open, audit every fire.** A hook that cannot reach the daemon in
   time injects nothing; memory never stops a prompt because Coffer is down.
   Every injection is an audit event naming the note, like every other
   delivery fire.

- **Pros.** Both moments need no authoring: they run on notes that already
  exist. Retrieval reached the largest part of the never-delivered half (15 of
  18 first attempts live, against 1 of 18 for the shipped index) at ~276
  tokens a run instead of ~11k emitted. It reuses the hooks and the explicit,
  audited installation that already exist, and keeps notes plain files.
- **Cons.** A hook on every prompt, whose latency the user feels. Retrieval
  adds up to 1.5 KB per prompt of lines that are sometimes off-topic (one run
  in the first round followed an off-topic line). A rule whose words the
  prompt does not share is missed: Node 20 stayed 0/3, because "run make
  verify" shares no word with the vitest note. The evidence is one model on
  one agent.
- **Why it wins.** It is the most the evidence supports without a mechanism a
  person must author. The remainder, a trap that lives in a command, is the
  honest limit (Option E).

### Option B — The session-start index alone, bounded (the design this replaced)

- **Pros.** One hook fire per session; nothing is added mid-session; the
  "pull, not push" principle keeps a single exception.
- **Cons.** Offline it delivers 18–22% of held needs even with the partition
  fix; live it avoided the first-attempt mistake in 1 of 18 runs. A budget that
  survives the agents' cut-offs holds about six lines out of hundreds, and a
  line read at the start of a session was the half of the failures that was
  delivered and still ignored.
- **Why it loses.** It is the baseline the eval measured.

### Option C — The whole index at start, untruncated

- **Pros.** 76% of held needs reached context in replay; no ranking.
- **Cons.** 30–45 KB cannot pass through either agent's hook output — Claude
  Code previews 2 KB of it and Codex cuts the middle past 2,500 tokens — and it
  costs ~6.9k tokens per Claude session. Even delivered in full, the baseline
  showed half the in-context rules ignored.
- **Why it loses.** It cannot be delivered, and delivery at the start was not
  enough when it was.

### Option D — Prompt-time retrieval alone

This is Option A without the start index.

- **Pros.** The best single fix for "never delivered" (56%), and strongest on
  Codex, whose misses are rules phrased close to the prompt.
- **Cons.** It cannot reach a rule the first message does not name, and a
  session whose first prompt is short gets nothing (prompts under three words
  retrieve nothing).
- **Why it loses.** The start index costs one fire and covers what a user
  would otherwise restate.

### Option E — A command-time guard on authored triggers (rejected)

A person attaches a command or error pattern to a note; `PreToolUse` denies
the first matching command once with the note as the reason; `PostToolUse`
adds the note after a matching error.

- **Pros.** 18/18 on the six scenarios at ~70 tokens a run, the only mechanism
  that reached "in context but not acted on" and the traps.
- **Cons.** Only a rule with a machine-matchable command can have a trigger,
  and someone must write, arm and maintain it. Measured in use: no trigger was
  ever armed, none held a command in thirty days, and one proposed trigger
  could not match what it meant. A guard that blocks needs precision, and
  nothing in the product could produce that precision without a person.
- **Why it loses.** Its measured value came from triggers an experimenter
  wrote by hand; its delivered value is zero. It also doubled the hook to four
  entries, and a deny that stops a command is the one place memory could
  interrupt work. A command-time reminder with no denial arrives after the
  command has run on Claude Code (1 of 6 first attempts on the scenarios that
  bit), so softening the guard does not rescue it.

### Option F — Triggers derived automatically from the notes' text

- **Pros.** No authoring.
- **Cons.** Rule-derived triggers fired about 25 notes per session with 0.8
  relevant; pruning the frequent ones removed the traps with them (traps
  52% → 16%).
- **Why it loses.** Precision is the whole value of a trigger that can block.

### Option G — Promote an explicit memory tool

- **Pros.** Nothing is pushed; the agent asks when it needs to.
- **Cons.** Retrieval that depends on the agent's initiative is the failure
  this layer has already measured: `coffer__recall` was called five times in
  its life, and recall or the guide skill appeared in about 15% of Claude
  sessions and 3% of Codex sessions.
- **Why it loses.** The problem was never that queries missed; it was that no
  query was made. The same holds for any mechanism that waits for a person's
  authoring.

### Option H — Rank with embeddings

- **Pros.** Better on paraphrased corrections and re-derived facts.
- **Cons.** Three points over BM25 on held failures (46% against 43%), one on
  all held needs, a 2.2 GB local model, and a reversal of the literal-search
  decision that removed embeddings from the product.
- **Why it loses.** The gain does not pay for the model; a lexical ranker is
  enough to start, and the eval set can measure a replacement later.

## Decision

**Memory reaches a session at two moments: a bounded index at session start,
and the top three relevant notes on each substantive prompt, ranked
lexically.** There is no command-time moment: no guard, no trigger, no
`PreToolUse` or `PostToolUse` hook. The hook is two entries, `SessionStart`
and `UserPromptSubmit`. Notes stay plain files; the ranking index is derived
and held in memory. Both agents receive the same payloads through JSON hook
output, and a channel turn receives them through the context Coffer composes.
Rules about every turn belong in the agent's always-loaded instructions, not
in memory delivery.

Rules a future change must respect:

- Every single injection stays under both agents' cut-offs: 9,500 UTF-8 bytes
  for the start index, 1.5 KB for a prompt's retrieval.
- Memory never blocks a prompt or a command. Delivered text is provenance plus
  fact, never an instruction to take a destructive step.
- A hook that cannot answer in time fails open.
- Every fire is audited and every hook is installed explicitly, per agent, and
  removably ([Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md)).
- The ranker is lexical until the eval set shows a replacement earns its
  cost.
- A mechanism that waits for a person to author or arm something is not added
  until a place to do it exists in the product and its use is measured.

## Consequences

- **Delivery is not only at session start.** Coffer delivers memory at the
  prompt as well, which is why "Pull, not push" is stated as "nothing reaches
  a session except through an installed, removable, audited hook". Knowledge
  stays pull: documents are not in the retrieval corpus, and adding them is a
  separate decision the replay can already inform.
- **Builds on the delivery rules** of [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md):
  the index at session start is the first of the two moments; that ADR's rule
  never to write an agent's native memory stands and is why per-turn rules are
  left to the user's own instructions.
- **Specs.** memory carries "Retrieve the notes a prompt names", "Fail open
  when Coffer cannot answer", "Word delivered notes as provenance plus fact"
  and "Retrieve the notes a prompt names for a channel turn". The vault holds
  no `memory-triggers/` directory.
- **Not built yet:** the persistence clause of the principles still says
  "nothing indexes, chunks or embeds" the files; the derived in-memory lexical
  ranker is not yet named there.
- **Not decided:** Codex compliance runs (the six scenarios at n >= 1) have
  not been made; Codex's effect rests on the fake-model verification of its
  delivery path. Traps that live only in a command and share no word with the
  prompt stay uncovered.
- **Costs.** A daemon round-trip on every prompt; up to ~1.5 KB per prompt.
- **Measurement.** The 107-case set stays the regression check for any change
  to ranking, budget or wording, replayed offline before live runs.
