## Why

The owner asked for Cursor, OpenCode and DeepSeek Harness to get every feature each can take. Chat, channels and scheduled tasks all run a turn through an agent's driver, and only Claude Code and Codex had one.

## What Changes

- A shared adapter runs a turn as one process of the agent's own one-shot command and maps its JSON lines onto turn events: `opencode run --format json`, `cursor-agent -p --output-format stream-json`, `dsh --profile headless --json`.
- Each agent gets its model and Coffer's system context the way it takes them: OpenCode through `--model` and an added `instructions` file, DeepSeek Harness through a `--patch` overlay, Cursor through `--model` and a fenced note ahead of the message.
- Failures quote the agent's stderr; a forgotten session is retried once fresh; a stopped turn ends its process.
- The three types get the `chat` feature, so chat, channels and scheduled tasks offer them. The agents guide's support table marks the column ✓.
- The `agent-cli` CI job runs a whole turn through the real OpenCode (1.x and 2.x) and DeepSeek Harness against a stand-in model server, and checks that Cursor accepts the command Coffer builds.
- Not in this change: their sessions list and terminal resume, Cursor's hooks, and a model connection for DeepSeek Harness.

## Capabilities

### Modified Capabilities

- `chat`: new requirement "Run a turn through the agent's one-shot command"; "Run Claude Code and Codex as subprocess providers on the type's one agent" points at it. The main spec is edited directly, so this change carries no delta.

## Impact

Backend chat infrastructure (`cli_turn`, `cli_provider`, `opencode_run`, `cursor_print`, `dsh_headless`, `drivers`), tests (integration with a stand-in CLI, agent-cli smoke turns), the ADR `cursor-opencode-and-deepseek-harness-chat-through-their-one-shot-commands`, and the docs-site agents, chat, channels and scheduled-tasks guides (en and zh).
