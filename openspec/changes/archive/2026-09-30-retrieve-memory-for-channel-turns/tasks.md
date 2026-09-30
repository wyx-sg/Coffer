## 1. Retrieval for channel turns

- [x] 1.1 `TurnRetrieval`: rank through `RetrievalService` keyed on the conversation, audit a `prompt` fire of the answering agent
- [x] 1.2 A per-turn `PromptMemory` seam: providers bind it for channel turns only; both adapters add the notes after the user's text
- [x] 1.3 Composition: `memory_turn_wiring` closures follow the feature switch and fail open; `wire_chat` hands them to both providers

## 2. Tests and docs

- [x] 2.1 Unit tests for the retrieval, the once-per-conversation rule and the fail-open seam
- [x] 2.2 Provider integration tests: the channel turn's prompt carries the notes, a web turn's does not
- [x] 2.3 Memory and channels guides, memory and chat architecture pages
