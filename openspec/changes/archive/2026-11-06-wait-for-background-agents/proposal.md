## Why

On 2026-11-05 a SeaTalk turn answered `(the agent returned no text)`. The agent
had started a background review sub-agent and ended its own turn; Coffer ended the
turn at that first result, closed the CLI, and the CLI stopped the sub-agent
after its 10-minute wait, so the work never came back. The owner decided Coffer
should wait for background work to finish, and say nothing when there is nothing
to say. The options are argued in ADR `a-claude-code-turn-waits-for-its-background-sub-agents`.

## What Changes

- A Claude Code result that arrives while a background sub-agent or workflow
  runs no longer ends the turn; the follow-up turn the agent is woken for does.
- The CLI's wait for background work is raised from 10 minutes to four hours.
- A turn whose agent wrote no text sends no reply (no placeholder line).

## Impact

- `claude_sdk_mapping`, `claude_sdk_agent`, `turn_finish`; chat and channels
  specs; channels docs.
