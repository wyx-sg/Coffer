# Cursor, OpenCode and DeepSeek Harness Chat Through Their One-Shot Commands

**Status**: Accepted
**Date**: 2026-11-23
**Deciders**: Yuxing Wu
**Related**: [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](cursor-opencode-and-deepseek-harness-are-supported-agents.md), [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [What Coffer Does for an Agent Follows From Its Facets](what-coffer-does-for-an-agent-follows-from-its-facets.md), [Automation Is a Scheduled Prompt](automation-is-a-scheduled-prompt.md), spec chat "Run a turn through the agent's one-shot command"

## Context

Chat, channels and scheduled tasks all run a turn through an agent's driver
facet. Until now only Claude Code (Claude Agent SDK) and Codex
(`codex app-server`, JSON-RPC over stdio) had one. The owner asked for Cursor,
OpenCode and DeepSeek Harness to get every feature they can take, so each
needs a driver.

What each product offers a program that wants to run a turn (checked on
2026-11-23 against OpenCode 1.19.6 and 2.3.2 and dsh 0.2.2-rc.5, each run end
to end against a stand-in model server; Cursor from its
[output-format reference](https://cursor.com/docs/cli/reference/output-format)):

| | One-shot command | Long-lived server | Session to continue | Model | Added system prompt |
| --- | --- | --- | --- | --- | --- |
| OpenCode | `opencode run --format json` | `opencode serve` (HTTP + SSE) | `--session <id>` | `--model provider/model` | `instructions` files, merged from `OPENCODE_CONFIG_CONTENT` |
| Cursor | `cursor-agent -p --output-format stream-json` | none | `--resume <id>` | `--model` | none |
| DeepSeek Harness | `dsh --profile headless --json` | ACP / SDK profiles (JSON-RPC) | `--session-id <id>` | `agent-default-model` in a `--patch` overlay | `system-prompt.personaSuffix` in the same overlay |

How comparable tools drive these CLIs: the projects that wrap several coding
agents behind one chat (for example the Rust crates `gate4agent` and
`harnesscli`, and GolemBot's Cursor adapter) start the agent's one-shot
command per message and parse its JSON lines. The agents' own documentation
recommends the same for scripts and CI (OpenCode's `run`, Cursor's print mode,
dsh's headless profile, whose README describes exactly this supervisor loop:
read the opening session id, resume with `--session-id`).

## Options

### A. One process per turn through the one-shot command (chosen)

Each turn starts the agent's one-shot command in the conversation's folder
and reads its JSON lines until it exits. The session id from the first line is
stored and passed back on the next turn.

- **Pro:** one shared adapter for all three. Only the command and the line
  shape differ, and each is a short module.
- **Pro:** nothing outlives a turn. A stopped turn ends its process; there is
  no server to keep alive, restart or sweep up, and no port.
- **Pro:** these are the commands the products document for automation, so a
  new release is least likely to break them. The CI job runs each real CLI
  through the adapter.
- **Con:** text arrives one finished message at a time, not as it is typed.
  Claude Code and Codex stream; on a phone the difference is small, because a
  channel sends whole messages anyway.
- **Con:** each turn pays the CLI's start-up (about a second for OpenCode and
  dsh here).

### B. Each product's long-lived server

`opencode serve`, dsh's ACP profile, and nothing for Cursor.

- **Pro:** text streams as it is written; no start-up per turn.
- **Con:** two protocols to implement and keep working, a server per agent to
  own, and Cursor still needs option A. Three code paths instead of one.

### C. The Agent Client Protocol (ACP) for all three

- **Con:** Cursor does not speak it; OpenCode's support differs between 1.x and
  2.x. Same cost as B with less coverage.

## Decision

Option A. The shared part (`infrastructure/chat/cli_turn.py`) spawns the
command through the daemon's child-process helper, so the orphan sweep can
find it, reads its stdout without a line-length limit, and ends the turn
honestly: a terminal line when the agent printed one, otherwise success on
exit status 0 and an error quoting stderr on any other. A stored session the
agent says it no longer has is retried once as a fresh one, as for Codex.

Per agent:

- **OpenCode**: `opencode run --format json --auto [--standalone] [--session
  <id>] [--model <p/m>] -- <message>`, stdin closed. 2.x needs `--standalone`
  to run inside the process Coffer started rather than a background service;
  the version is read once from `opencode --version`. 1.x waits on an open
  stdin, so it is closed. A bare model id is one of the connection's models
  and becomes `coffer/<id>`. The system context is written to a file for the
  turn and added to `instructions` through `OPENCODE_CONFIG_CONTENT`, which
  OpenCode merges over the user's config, keeping their instructions.
- **Cursor**: `cursor-agent -p --output-format stream-json --force --trust
  [--resume <id>] [--model <m>] -- <message>`. Cursor has no way to add a
  system prompt, so the context leads the message inside a
  `<coffer-context>` fence. It signs in with its own account.
- **DeepSeek Harness**: `dsh --profile headless [--patch <turn patch>] --json
  --permission-mode danger-full-access --approval-policy never [--session-id
  <id>] -`, the message on stdin. The turn's patch sets the model
  (`agent-default-model`) and the context (`system-prompt.personaSuffix`). A
  bare model id is a model of Coffer's `coffer` route.

All three run with the agent's full permissions, as Claude Code and Codex do:
the owner driving the conversation is the trust boundary.

## Consequences

- Chat, channels and scheduled tasks offer the three agents once one of them
  is registered and its program is on the user's PATH. The agents guide's
  support table marks the column ✓, and its test keeps it equal to the code.
- A reply from these agents grows a message at a time.
- A DeepSeek Harness user's own `personaSuffix` is replaced for Coffer's turns
  (not for their own runs).
- Their sessions list, terminal resume and hooks are separate work.
