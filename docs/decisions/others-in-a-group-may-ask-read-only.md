# Others in a Group May Ask the Bot, Read-Only, by Instruction

**Status**: Accepted
**Date**: 2026-10-28
**Deciders**: Yuxing Wu
**Related**: spec channels ("Let others in a group ask the bot", "Act in a group only on an addressed message from the owner", "Gate inbound traffic on sender identity");
[A Channel Answers Only Its Paired Owner, and Fails Closed in Groups](channel-owner-gate.md),
[Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md),
[A Channel's System Prompt Is a Fixed Channel Note Plus a Reply Style the Owner Can Rewrite](channel-prompt-fixed-note-and-editable-style.md)

## Context

The owner uses the bot in work groups to answer questions about their team's
systems — "why can't this user log in?", "what does this error mean?" — by
searching the knowledge base, the code and the team's documents and reading
logs. Colleagues in the same group ask the same kind of question, and today
they get "🚫 Only <bot>'s owners can use it here." The owner wants the bot to
answer them too, the way the owner would, without handing them the owner's
machine: an owner's turn may deploy, publish, change data, open tickets, send
messages and dispatch tasks, and a colleague's must not.

[A Channel Answers Only Its Paired Owner](channel-owner-gate.md) made "who may
speak" the only gate, because the agent behind it runs with full permissions.
So the questions are: who else may speak, where, how their turn is held to
reading, and whether that is on by default.

How comparable products draw the line:

- **Claude in Slack** answers anyone in the channels a workspace admin added it
  to; what it may touch follows the admin's connector settings, not who asked.
- **Slack AI** answers with the asking user's own permissions — it can only
  read what that person could read.
- **OpenClaw** (self-hosted agent gateway) gates group messages with a
  `groupPolicy` allowlist that blocks everyone not listed by default, and
  per-sender tool policies are the way to give a group a narrower agent.

Coffer is like OpenClaw (one person's agent on one person's machine) but the
groups are work groups where the owner already knows everyone, which is the
Claude-in-Slack situation.

## Options Considered

### Option A — A switch, on by default; others are answered in groups an owner already used; read-only is an instruction to the agent (chosen)

How it works: `others_can_ask` (default on). An addressed group message from a
named non-owner, in a group that already has a peer row because an owner
addressed the bot there, drives a turn in that group's conversation. Its
origin block says `asker: not an owner (read-only)`, and the group's channel
note tells the agent to answer and run read-only checks but change nothing and
start no work on their word. Their commands and taps are refused in code.

Pros: works with every agent and every tool today; the owner decides which
groups are open by using the bot there; one switch closes it again; commands
and buttons, which Coffer itself executes, are gated in code.

Cons: the agent still holds every permission, so a colleague who talks it into
a write gets one — prompt injection is not excluded. The limit is as good as
the model's compliance.

Wins because it gives the owner the behaviour now at the cost of one
instruction, and leaves room for Option B without changing the switch, the
gate or the origin line.

### Option B — Read-only enforced by Coffer: a non-owner's turn runs with a reduced tool set

How it works: the same admission, but the turn is started with write tools
disabled — no shell, no file writes, only the read-only Coffer tools and
platform reads.

Pros: a real boundary; injection cannot reach a write tool that is not there.

Cons: "read-only" is not a property of a tool: the shell is how the agent
reads logs and greps code, and a CLI the owner installed may read or write
depending on its arguments. Doing it properly means per-tool read/write
classification for Claude Code and Codex, a separate session per asker so the
group conversation's tools do not change turn to turn, and work in both agent
drivers.

Not now: the owner chose to ship the instruction first and add enforcement
later. Option A's switch and origin line are what Option B would build on.

### Option C — Keep owners only; add colleagues as owners

How it works: no change; a colleague who should be answered is paired as an
owner.

Pros: nothing new to trust.

Cons: an owner can do everything, so the only way to let a colleague ask is to
let them deploy. Pairing needs their direct chat with the bot first.

Loses because it is the problem the owner asked to solve.

### Option D — Off by default, opt in per channel

How it works: as Option A, but `others_can_ask` defaults to off.

Pros: an upgrade changes nothing; the safer default, as OpenClaw chooses.

Cons: the owner's groups are work groups with colleagues they know, where
being answered is the point. The admission is already narrow — only groups an
owner has addressed the bot in, only addressed messages, only named senders —
so a stranger cannot reach the bot by adding it to a new group.

Loses on the owner's call: on by default, with the switch as the guard against
abuse.

## Decision

A channel's `others_can_ask` setting, on by default, lets someone who is not an
owner ask the bot in a group an owner has already addressed it in. Their
addressed, named message drives a turn marked `asker: not an owner (read-only)`
in its origin, and the group's channel note holds the agent to answers and
read-only checks for them. Their commands are refused with one line and their
taps stay refused. The read-only limit is an instruction, not a sandbox.

Rules a future change must respect:

- A group no owner has addressed the bot in stays closed to everyone else.
- A sender the transport could not name is never admitted.
- A non-owner's turn always carries the origin line, so the agent and any
  later enforcement can tell it apart.
- Commands and button taps, which Coffer executes itself, stay owner-only.

## Consequences

- The owner gate of [A Channel Answers Only Its Paired Owner](channel-owner-gate.md)
  now has one opening: for a non-owner it answers "may this person ask?", and
  the agent's instructions answer "may they make it act?".
- A colleague's question and the owner's follow-up share the group thread's
  conversation, so an owner can pick up a colleague's request with "do it".
- The vault skill that guards writes repeats the rule, so an agent that loads
  it on a write path checks who asked.
- Enforced by: `application/channel/inbound_gate.py`,
  `application/channel/inbound.py`, `domain/channel/rich_content.py`,
  `domain/chat/channel_prompt.py`, `application/channel/prompt_note.py`.
