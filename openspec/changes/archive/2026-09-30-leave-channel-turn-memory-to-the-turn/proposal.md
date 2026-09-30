## Why

Coffer composes a channel-driven turn's memory itself: the index in the system prompt and the notes the prompt names after the prompt. The agent process it spawns for that turn still loads the agent's own settings, so Coffer's installed memory hook fires inside it too. The Agent SDK loads the user's settings, and `codex app-server` runs a trusted `hooks.json` on `SessionStart` and `UserPromptSubmit`. So on a connected agent, a channel turn got the index twice and the prompt's notes twice, because the hook's ledger (keyed on the agent's session id) and the turn's ledger (keyed on the conversation) never saw each other's deliveries. Every such prompt was also audited twice, once as a `UserPromptSubmit` fire and once as a `ChannelTurn` fire, so the Memory page counted it twice.

## What Changes

- Coffer marks the environment of the agent process it spawns for a channel turn (`COFFER_CHANNEL_TURN=1`), for both Claude Code and Codex. A turn the developer drives is not marked.
- `coffer memory hook` answers nothing, and records nothing, on `SessionStart` and `UserPromptSubmit` in a marked process. The turn owns those two moments. `PreToolUse` and `PostToolUse` still go through the hook, because the turn path answers neither.
- The turn path audits its index as the turn's `session_start` fire, with event `ChannelTurn` and the conversation as the session. Its prompt fire is unchanged, so each moment of a channel turn is delivered once and counted once.

## Capabilities

### New Capabilities

### Modified Capabilities
- `memory`: a channel turn's own hook stands down on the two moments the turn carries, and the turn audits its index.

## Impact

- Backend: `domain/channel_turn.py` (new, kind-agnostic), `domain/memory/delivery.py`, `surfaces/cli/memory_hook_cmd.py`, both chat providers, `infrastructure/chat/adapter_support.py`, `application/memory/turn_retrieval.py`, `surfaces/http/{memory_turn_wiring,memory_wiring,app}.py`.
- Tests: the hook CLI, both provider integration tests, the turn retrieval and composer unit tests.
- Docs: the memory architecture page.
