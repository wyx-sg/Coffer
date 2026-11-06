# An Agent Notifies the Owner Through a Built-in Tool, Direct Chat Only

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [An Agent Asks the Owner in Its Reply, Not in a Question Card](ask-in-the-reply-not-in-a-card.md), [A Channel Reply Names Its Files, and the Files Follow It](a-reply-names-its-files-and-they-follow-it.md), spec channels "Let an agent message the owner's direct chat", spec channels "Notify the paired owner on demand", [principles](../../docs-site/architecture/principles.md) ("Not a second agent")

## Context

A channel lets the owner reach an agent on this machine from their phone. The
other direction did not exist for an agent: one working in a terminal, or in the
agent's own scheduled task, could not tell the owner it was done. Coffer had
only REST `POST /api/v1/channels/{uid}/notify`, which needs the daemon's access
token and the channel's uid, neither of which an agent should be juggling.

The principles say recurring work is the agent's own scheduled task, not a
Coffer scheduler. What such a task lacks is a way to reach the phone: that part
needs the channel's credentials, which only Coffer holds. The chat and channel
gap review (2026-11-06) found the gap. Comparable bridges all give the agent
this: cc-connect has `cc-connect send --file/--image`, Claude Code Channels has
a `reply` tool, claude-code-telegram has `NOTIFICATION_CHAT_IDS`.

## Options Considered

### Option A — A built-in MCP tool, offered in every session, owner's direct chat only (chosen)

`coffer__channel_notify` takes text, optional files by absolute path and an
optional channel name. It sends to the owner's direct chat and never to a group.

Pros: every agent already reaches Coffer through its MCP entry, so there is
nothing to install or configure. It works the same for Claude Code and Codex. No
token is handed to the agent: the gateway is the capability. Direct chat only
means a prompt-injected agent cannot post into a group the owner shares with
other people.

Cons: one more tool in every session's list (a short one). A noisy agent could
send many messages; the owner's remedy is the agent's own instructions.

### Option B — A CLI command (`coffer channel notify`)

Pros: scriptable outside an agent.

Cons: the agent has to find and shell out to the command, and the CLI needs the
daemon token. The REST route already serves scripts.

Loses because it does the same job less directly for the caller that needs it.

### Option C — A Coffer scheduler that runs the job and posts the result

Pros: one place for schedules and delivery.

Cons: rebuilds what each agent's own scheduled tasks already do, which the
principles' "Not a second agent" clause declines.

Loses on the principle.

### Option D — Let the tool post to any paired chat, groups included

Pros: an agent could announce a result to a team group.

Cons: anyone who can steer the agent (a web page, a file, a colleague in a group)
could make it post private material to a group. Nobody needs it now.

Loses on safety; a group target can be added later as an explicit owner setting.

## Decision

`coffer__channel_notify` is a built-in tool listed in every MCP session. It sends
text, then up to 10 files, to the owner's direct chat of a running, paired
channel. With several such channels the agent must name one; with none the call
says to set one up. It never reaches a group.

## Consequences

- An agent's own scheduled tasks, and terminal work, can report to the phone
  without a Coffer scheduler.
- A future group target must be an explicit owner choice, not a tool argument.
- Enforced by `application/channel/notify_tool.py`, wired in
  `surfaces/http/channel_wiring.py`.
