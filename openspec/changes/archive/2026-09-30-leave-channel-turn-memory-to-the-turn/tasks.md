## 1. One owner for each moment of a channel turn

- [x] 1.1 `domain/channel_turn.py`: the environment mark on a process Coffer spawned for a channel turn
- [x] 1.2 Both providers set the mark on a channel turn's process, merged over the daemon's environment
- [x] 1.3 `coffer memory hook` answers nothing on `SessionStart` and `UserPromptSubmit` in a marked process
- [x] 1.4 `TurnRetrieval.index_for_turn` composes the index and audits it as the turn's `session_start` fire

## 2. Tests and docs

- [x] 2.1 Hook CLI: a marked process sends only the guard to the daemon; an unmarked one sends all three
- [x] 2.2 Provider integration tests: a channel turn's process is marked, a web turn's is not
- [x] 2.3 Unit tests: the turn's index equals the hook's and is audited once; an empty index records nothing
- [x] 2.4 Memory architecture page
