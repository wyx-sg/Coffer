## Why

Per-prompt memory retrieval (BM25, top three) reaches an agent through Coffer's `UserPromptSubmit` hook. A channel-driven turn runs no hook of Coffer's: Coffer spawns the agent through the Agent SDK or `codex app-server` and composes its context itself. Such a turn received the memory index in its system prompt, but never the notes its prompt named.

## What Changes

- A channel-driven turn's prompt is ranked by the same `RetrievalService` the hook answers through, with `conversation:<id>` as the session in the ledger, so a note is given once per conversation.
- The notes it finds are added after the user's text in the prompt the agent receives, for both Claude Code and Codex. The message stored in the conversation is unchanged.
- Each delivery is audited as a `prompt` fire of the answering agent, with event `ChannelTurn`.
- The retrieval follows the `memory` feature switch per turn and fails open.
- The channel-turn memory closures move to `surfaces/http/memory_turn_wiring.py`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `memory`: channel-driven turns get prompt-time retrieval.

## Impact

- Backend: `application/memory/turn_retrieval.py`, `infrastructure/chat/prompt_memory.py`, both agent adapters and providers, `infrastructure/chat/drivers.py`, `surfaces/http/{memory_turn_wiring,memory_wiring,chat_wiring,chat_provider_wiring,app}.py`.
- Tests: `tests/unit/memory/test_turn_retrieval.py`, the SDK and Codex provider integration tests.
- Docs: the memory and channels guides, the memory and chat architecture pages.
