# A Claude Code Turn Waits for Its Background Sub-Agents

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`](driving-agents-through-sdk-and-app-server.md), spec chat "Wait for a Claude Code turn's background sub-agents", spec channels "Show a turn's working state as one status line"

## Context

On 2026-11-05 a SeaTalk chat answered `(the agent returned no text)` twice. The
daemon log for the first one shows why: `Background tasks still running 10m
after the last turn (subagent "Independent review of automation design");
stopping them.` The agent had started a background review sub-agent and ended
its own turn with no text. Coffer treated that first result as the end of the
turn, closed the CLI's input, and the CLI waited its default 10 minutes
(`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`), then stopped the sub-agent. The
review never came back, and the reply was the placeholder.

In stream-json mode the CLI wakes the agent when a background sub-agent ends and
runs a follow-up turn whose text is the real answer; the SDK marks it as a
`ResultMessage` with a `task-notification` origin. Coffer stopped reading at the
first result, so it could never see it.

How comparable products handle it: Claude Code's own terminal UI keeps the
session open and shows the follow-up when a background task reports in; the
Agent SDK's `receive_response()` stops at the first result and leaves the caller
to keep reading for injected turns; Codex has no background hand-back, a
sub-agent's work returns through the parent's own messages.

## Options Considered

### Option A — Hold the result while a background sub-agent runs; end on the follow-up (chosen)

Track sub-agent and workflow tasks from the SDK's task messages. A result that
arrives while one is running is held back; the turn ends on a result that arrives
with none running. Raise the CLI's wait to one hour. If the stream ends first,
the held result ends the turn.

- ✅ The answer the owner asked for arrives, in the same reply, as one turn.
- ✅ Uses only what the SDK reports; no polling and no extra model turn.
- ⚠️ A sub-agent that hangs keeps the turn open for up to an hour; `/stop` ends it.
- ⚠️ Relies on the SDK's task messages; a task type it never reports is not waited for.

### Option B — Keep ending at the first result; tell the owner the work was cut off

- ✅ Smallest change; no turn ever stays open longer than the agent's own work.
- ❌ The owner still loses the review: the sub-agent is stopped and only the
  explanation arrives. This is the failure that was reported.

### Option C — Forbid background sub-agents in channel turns

Disallow the background mode for the sub-agent tool in channel conversations.

- ✅ Removes the case at its source; every turn is one result.
- ❌ Takes a capability away from the owner's agent in the chat that is most
  often away from the desk, and does not cover background workflows.

### Option D — Ask the agent for a summary when a turn ends with no text

After an empty result, send the same session a "please summarise" turn.

- ✅ Gives text even when no sub-agent is involved.
- ❌ An extra model turn per empty result, and when a sub-agent is still running
  the summary can only say "waiting".

## Decision

Option A. The owner's rule (2026-11-06): Coffer waits for background work to
finish, and where there is nothing to say it says nothing. The second half is
channels: a turn whose agent wrote no text sends no reply, with no placeholder.

## Consequences

- `claude_sdk_mapping` tracks the running sub-agent and workflow task ids and
  holds a successful result while any runs; `claude_sdk_agent` sends the held
  result if the stream ends first and sets the CLI's wait to one hour unless the
  environment already sets it.
- A background shell command is not waited for: it does not wake the agent and
  may never end.
- A turn can now run past an hour of wall-clock only through the agent's own work.
