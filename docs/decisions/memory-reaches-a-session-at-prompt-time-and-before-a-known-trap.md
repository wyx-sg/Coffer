# Memory Reaches a Session at Three Moments: an Index at Start, Retrieval per Prompt, and a Guard Before a Known Trap

**Status**: Proposed
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md), [Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md), [Knowledge Is a Directory of Markdown Files, Not an Index](knowledge-is-plain-files.md), [Storage Is Five Classes by Nature; Whether a Class Syncs Is Policy](storage-is-five-classes-by-nature.md), [Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md), [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), [principles](../../docs-site/architecture/principles.md) (Persistence), design principle [Pull, not push](../../docs-site/architecture/design-principles.md#pull-not-push), research note [agent memory](../research/agent-memory.md), spec memory "Deliver the index and the notes path at session start", spec memory "Bound delivery and prefer the current repository", spec memory "Deliver to channel turns through the system prompt", spec memory "Install delivery hooks explicitly and removably", spec memory "Audit every delivery fire", spec memory "Expose no memory tool and name the memory root at session start", spec memory "Keep the memory tree derived and local"

## Context

Coffer's memory layer reads what Claude Code and Codex learned, distils it into
notes of its own, and hands them back
([Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md)).
The handing back has been one thing: the **whole index at session start**,
through a hook the user installs per agent, as the single declared exception to
the design principle [Pull, not push](../../docs-site/architecture/design-principles.md#pull-not-push).
Nothing reaches a session after its first moment. This ADR decides when memory
reaches a session, and on what evidence.

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
  `global` lines. The cap is now 9,500 UTF-8 bytes (shipped).
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
  `$PPID` — and was fixed on 2026-09-30.

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

## Options Considered

### Option A — Three moments: a bounded index at start, lexical retrieval per prompt, and a once-per-session guard on authored triggers (chosen)

1. **Session start: the bounded index.** As shipped: `global`'s index and the
   current repository's, repository lines preferred, at most 9,500 UTF-8
   bytes, naming the memory root and the notes directory. It covers the rules a
   user would otherwise restate in the first message.
2. **Each prompt: lexical retrieval.** A `UserPromptSubmit` hook asks the
   daemon to rank every partition's notes — title, description, search terms
   and body — against the prompt with BM25 (CJK text as bigrams), and injects
   the top **k = 3** as each note's index line and path, at most **1.5 KB**,
   only above a **relevance floor**. Prompts under three words ("continue",
   "继续") trigger nothing, and a note already injected in the session is not
   injected again. The ranking index is held in memory, rebuilt from the note
   files when they change, and is derived state; nothing chunks or embeds the
   notes.
3. **Before a known trap: an authored guard.** A person may attach
   **triggers** to a note — a command pattern, an error pattern, or both —
   written by hand in the UI or the CLI. Distil may propose a trigger; it is
   armed only when a person accepts it. A command pattern is matched against
   the program each shell segment actually executes (after any `VAR=value`
   prefix), so `cat scripts/e2e.sh` does not trip a trigger on `e2e`. The first
   matching command in a session is **denied once**, with the note as the
   reason; the agent's next attempt passes, so a deliberate re-run is never
   stuck. An error pattern, matched in `PostToolUse`, adds the note as context
   and never blocks. Triggers are authored content, so they live in the vault
   (`vault/memory-triggers/`, one file per trigger) beside the derived notes,
   never inside them, and survive a rebuild of the memory tree
   ([Storage Is Five Classes by Nature](storage-is-five-classes-by-nature.md)).
4. **Wording.** Every injected note reads as provenance plus fact: "Coffer
   memory, a note the user wrote (`<file>`): the user's standing rule is: …".
   Nothing delivered at command time instructs a destructive step; a rule that
   authorises an action is delivered at the prompt.
5. **Per-turn rules are not memory's job.** A rule about every reply — its
   language, its tone — belongs in the instructions the agent loads on every
   turn (`CLAUDE.md`, `AGENTS.md`), which the user owns and Coffer does not
   write, as it does not write the agent's memory.
6. **Both agents, same payloads.** Claude Code and Codex get the same four
   events through JSON `additionalContext` — `SessionStart`,
   `UserPromptSubmit`, `PreToolUse` (the `deny`) and `PostToolUse` — installed
   with the absolute path of the `coffer` binary, guarded once per session on
   the hook's `session_id`, every payload under both agents' cut-offs. An
   untrusted Codex hook is reported as untrusted, not as installed. A
   channel-driven turn gets the index and the per-prompt retrieval through the
   system-prompt append the turn platform already composes, and the guard
   through the hooks the driven agent loads.
7. **Fail open, audit every fire.** A hook that cannot reach the daemon in
   time injects nothing and blocks nothing; memory never stops a prompt or a
   command because Coffer is down. Every injection, denial and context fire is
   an audit event naming the note, as every delivery fire is today.

- **Pros.** It is the combination the evidence supports: 18/18 against 1/18 on
  the first attempt, at ~320 tokens a run instead of ~11k emitted. Each layer
  covers what the others cannot — the start index the first message, retrieval
  the rules a prompt names, the guard the traps that live in a command. It
  reuses the hooks and the explicit, audited installation that already exist,
  and keeps notes plain files.
- **Cons.** A hook on every prompt and every command, whose latency the user
  feels. Triggers cost a person's authoring, and a loose pattern denies a
  harmless command once per session. Retrieval adds up to 1.5 KB per prompt of
  lines that are sometimes off-topic (one run in the first round followed an
  off-topic line). The evidence is one model on one agent.
- **Why it wins.** Every other option leaves one of the two failure halves
  untouched.

### Option B — The session-start index alone, bounded (the design this replaces)

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

- **Pros.** The best single fix for "never delivered" (56%), and strongest on
  Codex, whose misses are rules phrased close to the prompt.
- **Cons.** It cannot see a trap that appears mid-task: Node 20 stayed 0/3,
  because the prompt "run make verify" does not name the note's words, and most
  Claude cases were exactly such traps (Claude 19% in replay).
- **Why it loses.** It leaves the largest category to chance.

### Option E — The command-time guard alone

- **Pros.** 18/18 on the six scenarios at ~70 tokens a run.
- **Cons.** Only a rule with a machine-matchable command can have a trigger;
  tool-routing rules, framing and platform facts have none. On the scenarios it
  was measured on, every rule had a hand-written trigger, which is its ceiling;
  with retrieval beside it the agent needed half as many blocks.
- **Why it loses.** It needs retrieval for everything a command does not name.

### Option F — A command-time reminder instead of a denial

Inject the note as `additionalContext` at `PreToolUse` without blocking.

- **Pros.** Never interrupts the agent.
- **Cons.** On Claude Code the context arrives after the command has run, so it
  can only help recovery: 1 of 6 first attempts on the scenarios that bit, 4 of
  10 overall. The imperative form of one such note was treated as prompt
  injection.
- **Why it loses.** It arrives after the damage. It survives as the
  `PostToolUse` error context in Option A, where after is the right time.

### Option G — Triggers derived automatically from the notes' text

- **Pros.** No authoring.
- **Cons.** Rule-derived triggers fired about 25 notes per session with 0.8
  relevant; pruning the frequent ones removed the traps with them (traps
  52% → 16%).
- **Why it loses.** Precision is the whole value of a trigger that can block.
  Distil proposing and a person accepting keeps the authoring cheap without
  arming noise.

### Option H — Rank with embeddings

- **Pros.** Better on paraphrased corrections and re-derived facts.
- **Cons.** Three points over BM25 on held failures (46% against 43%), one on
  all held needs, a 2.2 GB local model, and a reversal of the literal-search
  decision that removed embeddings from the product.
- **Why it loses.** The gain does not pay for the model; a lexical ranker is
  enough to start, and the eval set can measure a replacement later.

### Option I — Promote an explicit memory tool

- **Pros.** Nothing is pushed; the agent asks when it needs to.
- **Cons.** Retrieval that depends on the agent's initiative is the failure
  this layer has already measured: `coffer__recall` was called five times in
  its life, and recall or the guide skill appeared in about 15% of Claude
  sessions and 3% of Codex sessions.
- **Why it loses.** The problem was never that queries missed; it was that no
  query was made.

## Decision

**Memory reaches a session at three moments: a bounded index at session start,
the top three relevant notes on each substantive prompt ranked lexically, and,
before a command that a person has marked as a known trap, one denial per
session that carries the note as its reason.** Notes stay plain files; the
ranking index is derived and held in memory; triggers are authored by a person
and stored in the vault. Both agents receive the same payloads through JSON
hook output, and a channel turn receives them through the context Coffer
composes. Rules about every turn belong in the agent's always-loaded
instructions, not in memory delivery.

Rules a future change must respect:

- Every single injection stays under both agents' cut-offs: 9,500 UTF-8 bytes
  for the start index, 1.5 KB for a prompt's retrieval.
- A trigger blocks at most once per session, matches the executing command
  and never text a command merely mentions, and is never armed without a
  person's acceptance.
- Delivered text is provenance plus fact, never an instruction to take a
  destructive step.
- A hook that cannot answer in time fails open.
- Every fire is audited and every hook is installed explicitly, per agent, and
  removably ([Coffer's Agent Hooks Are Marker-Scoped, Explicit, Audited and Repaired When Stale](agent-hook-installation.md)).
- The ranker is lexical until the eval set shows a replacement earns its
  cost.

## Consequences

- **Reverses** the design principle "Pull, not push" for memory: Coffer now
  delivers memory at the prompt and before a command, not only at session
  start. Knowledge stays pull: documents are not in the retrieval corpus, and
  adding them is a separate decision the replay can already inform.
- **Revises, on acceptance,** [Aggregate the Agents' Memory; Never Write It](aggregate-agent-memory-never-write-it.md)
  in its delivery rules (items 5 and 6), which move here; its rule never to
  write an agent's native memory stands and is why per-turn rules are left to
  the user's own instructions.
- **Principles** (an amendment proposed in its own change). The Persistence clause's "nothing indexes, chunks or embeds
  them" admits the derived, in-memory lexical index this delivery ranks with,
  and a clause records the delivery model.
- **Specs.** memory gains requirements for prompt-time retrieval, authored
  triggers and the once-per-session denial; "Deliver the index and the notes
  path at session start" and "Bound delivery and prefer the current
  repository" stay; "Expose no memory tool and name the memory root at session
  start" stays. vault-sync learns `vault/memory-triggers/`. web-ui gains the
  trigger editor on a note and the proposed-trigger review.
- **Before acceptance.** The Codex compliance runs — the six scenarios at n ≥ 1
  — are added to this ADR's Context.
- **Costs.** A daemon round-trip on every prompt and every shell command; a
  per-note authoring step for traps; up to ~1.5 KB per prompt.
- **Measurement.** The 107-case set stays the regression check for any change
  to ranking, budget or wording, replayed offline before live runs.
