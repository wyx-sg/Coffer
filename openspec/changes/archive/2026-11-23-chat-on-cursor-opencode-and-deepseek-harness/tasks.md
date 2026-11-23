## 1. Driver

- [x] 1.1 Shared one-shot adapter: spawn through `ChildProcess`, unbounded line reads, terminal from the line or the exit status, stderr on failure, forgotten-session retry, cancel ends the process
- [x] 1.2 OpenCode (`--standalone` for 2.x from `--version`, stdin closed, `OPENCODE_CONFIG_CONTENT` instructions, `coffer/<id>` models)
- [x] 1.3 Cursor (`--force --trust`, fenced context)
- [x] 1.4 DeepSeek Harness (message on stdin, turn patch with model and `personaSuffix`)
- [x] 1.5 Bind the three drivers; `features` gains `chat`

## 2. Tests

- [x] 2.1 Integration tests with a stand-in CLI for each scenario
- [x] 2.2 agent-cli smoke: real OpenCode 1.x/2.x and dsh run a turn and resume it; Cursor accepts the command

## 3. Docs

- [x] 3.1 ADR `cursor-opencode-and-deepseek-harness-chat-through-their-one-shot-commands`
- [x] 3.2 Spec chat requirement
- [x] 3.3 docs-site agents, chat, channels, scheduled tasks (en + zh)
