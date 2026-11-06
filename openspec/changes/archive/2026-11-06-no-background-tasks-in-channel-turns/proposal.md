## Why

PR #704 made a Claude Code turn wait for its background sub-agents. In a chat
nobody sees a background task run and its result arrives after the reply, so the
owner agreed (2026-11-06) that a channel conversation should not start them at
all; sub-agents the agent runs in the foreground stay. A turn that still ends
with no text now leaves a log line, since it sends no reply.

## What Changes

- A channel conversation's Claude Code turn sets `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.
- An empty turn logs `channel.turn.empty_reply`.

## Impact

- `claude_sdk_provider`, `claude_sdk_agent`, `turn_finish`; chat spec; docs-site; ADR
  `a-claude-code-turn-waits-for-its-background-sub-agents`.
