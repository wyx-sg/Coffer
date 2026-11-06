## 1. Model

- [x] 1.1 `ScheduledTaskConfig.chat` optional; a task in no chat is `fresh`, names its agent, mentions no one; a follow-up keeps its chat
- [x] 1.2 Schedule `timezone` (IANA, validated); `next_slot` and `grace_for` on that zone's wall clock; a skipped local time runs once at the first valid time after it
- [x] 1.3 Run outcome `done`

## 2. Runs

- [x] 2.1 `FreshTurnPort`: a new conversation (agent, model, directory or home) whose one turn carries the task block; the run closes `done`, `failed` or `stopped` from the turn's end
- [x] 2.2 Opening block names no chat and says the reply goes nowhere and how to notify the owner
- [x] 2.3 Pause notice, `/status` and the daily report's waiting list skip tasks in no chat

## 3. Surfaces

- [x] 3.1 REST: the task's `chat` optional; `channel_name` empty for no chat; `outcome` gains `done`; `make contracts`
- [x] 3.2 CLI: `coffer task add` help names the optional chat and timezone (its body is the config)
- [x] 3.3 Web UI: dialog "Runs in" (a chat / no chat) with agent, model and directory, and a timezone; list and detail say "No chat"
- [x] 3.4 Docs en/zh; ADR; principles

## 4. Tests

- [x] 4.1 acceptance(channels, …) for every new and changed scenario
- [x] 4.2 `make verify`
