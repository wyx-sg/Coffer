# Agent chat clients: how other products do it

**Feature**: a GUI (web, desktop or mobile) that drives locally installed coding-agent CLIs (Claude Code, Codex) as a chat — sending turns, streaming tool events, queueing and interrupting, resuming sessions, keeping many conversations, and mirroring a conversation that is also driven from elsewhere (phone, IM) · **Coffer spec**: [chat](../../openspec/specs/chat/spec.md) · **Related ADRs**: [Chat Is a Single-Owner Live Mirror](../decisions/chat-single-owner-live-mirror.md), [Driving Agents Through the SDK and App-Server](../decisions/driving-agents-through-sdk-and-app-server.md), [Managed Agents Run With Full Permissions](../decisions/managed-agents-run-with-full-permissions.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (official docs, repo source files read via the GitHub API, changelogs). Star counts from `api.github.com` on 2026-09-24.

Products are grouped by layer: the two vendor protocols first (everything else builds on them), then the vendor GUIs, then the cross-vendor protocol (ACP), then third-party clients sorted roughly by adoption.

| Product | Stars (2026-09) | Status |
|---|---|---|
| Claude Code (anthropics/claude-code) | ~148k | active |
| Codex (openai/codex) | ~126k | active |
| Orca (stablyai/orca) | ~77k | active |
| Cline (cline/cline) | ~69k | active (own agent, not a CLI driver) |
| AionUi (iOfficeAI/AionUi) | ~33k | active |
| Vibe Kanban (BloopAI/vibe-kanban) | ~28k | company shut down 2026-04; community-maintained |
| Happy (slopus/happy) | ~24k | active |
| opcode (winfunc/opcode, ex-Claudia) | ~22k | code dormant since 2025-10 |
| cc-connect (chenhg5/cc-connect) | ~16k | active |
| claudecodeui / CloudCLI (siteboon/claudecodeui) | ~14k | active |
| Claude Agent SDK (Python / TS) | ~8.2k / ~1.8k | active |
| CodexMonitor (Dimillian/CodexMonitor) | ~4.3k | quiet since 2026-03 |
| desktop-cc-gui (zhukunpenglinyutong) | ~4.4k | active |
| Agent Client Protocol spec | ~4.3k | active (v1 stable, v2 alpha) |
| codeg (xintaofei/codeg) | ~3.7k | active |
| Crystal (stravu/crystal) → Nimbalyst | ~3.1k → ~1.8k | Crystal deprecated 2026-02 |
| Conductor (Melty Labs) | closed source | active |

---

## 1. Claude Code's own driving surface: stream-json and the Agent SDK

Every serious Claude Code GUI ends up on one of two variants of the same wire: the CLI's **stream-json** mode, either raw or wrapped by the **Claude Agent SDK**.

**Process model.** The SDK is "a library that runs the Claude Code binary" ([overview](https://code.claude.com/docs/en/agent-sdk/overview)). The Python SDK prefers a CLI bundled inside the wheel, and always launches `claude --output-format stream-json --verbose --input-format stream-json`, even for a one-shot string prompt, so that large config (agents, hooks) travels in an `initialize` control request rather than argv ([subprocess_cli.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/transport/subprocess_cli.py)). Options map to flags: `--permission-mode`, `--permission-prompt-tool`, `--resume`, `--continue`, `--fork-session`, `--session-id`, `--include-partial-messages`, `--mcp-config`, `--model`, `--effort`.

**Input.** One JSON line per user message on stdin: `{"type":"user","message":{"role":"user","content":...},"parent_tool_use_id":null,"session_id":...}`; `content` may be a block array with base64 images. Optional fields include `uuid` (to correlate receipts) and `shouldQuery:false` (append to the transcript without starting a turn) ([TS reference](https://code.claude.com/docs/en/agent-sdk/typescript)). `--replay-user-messages` echoes accepted user lines back on stdout with `isReplay:true`, which gives a client an acknowledgement that the agent actually took the message ([headless](https://code.claude.com/docs/en/headless)).

**Output.** A union of ~36 message types ([TS reference](https://code.claude.com/docs/en/agent-sdk/typescript)): `system/init` (session id, model, tools, MCP servers, permission mode, slash commands, and a `capabilities` array for feature detection), `assistant` (text / tool_use / thinking blocks), `user` (tool_result, with a structured `tool_use_result`), `stream_event` (raw token deltas when `--include-partial-messages` is on; main thread only, with `ping` keep-alives), and a terminal `result` (subtype `success` / `error_max_turns` / `error_during_execution` / …, plus `session_id`, `usage`, `total_cost_usd`, `permission_denials`, `user_message_uuids`, `queued_turn_count`). Subagent traffic carries `parent_tool_use_id`, so a client can nest it under the `Task` tool call.

**Control protocol.** Everything interactive is a `control_request` / `control_response` pair keyed by `request_id` ([query.py](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py)):
- client → CLI: `initialize`, `interrupt`, `set_permission_mode`, `set_model`, `rewind_files`, `mcp_status` / `mcp_reconnect` / `mcp_toggle`, `stop_task`, `get_context_usage`;
- CLI → client: `can_use_tool` (tool name, input, `permission_suggestions`, `tool_use_id`, `blocked_path`, `decision_reason`), `hook_callback`, `mcp_message` (in-process MCP servers).
- A permission answer is `{"behavior":"allow","updatedInput":…,"updatedPermissions":[…]}` or `{"behavior":"deny","message":…,"interrupt":bool}`. The CLI blocks on the reply, so stdin must stay open while any callback is registered. After a transport gap, `reinitialize()` re-sends `initialize`, and `initialize` returns still-unresolved permission requests — the answer handler must be idempotent per request id ([TS reference](https://code.claude.com/docs/en/agent-sdk/typescript)).

**Permissions.** Evaluation order is hooks → deny rules → ask rules → permission mode → allow rules → `canUseTool` ([permissions](https://code.claude.com/docs/en/agent-sdk/permissions)). Modes: `default`, `acceptEdits`, `plan`, `bypassPermissions`, `dontAsk` (deny instead of asking), `auto` (classifier decides). `AskUserQuestion` always reaches the callback, even in bypass mode; answers go back in `updatedInput.answers` ([user input](https://code.claude.com/docs/en/agent-sdk/user-input)). The raw-CLI equivalent is `--permission-prompt-tool <mcp tool>` (older) or `--permission-prompt-tool stdio` (the control protocol), and `--permission-prompts none` for unattended runs ([CLI reference](https://code.claude.com/docs/en/cli-reference)).

**Queueing and interrupt.** Streaming-input mode is described as the preferred mode precisely because it supports "queued messages" and "real-time interruption"; single-message mode does not ([streaming vs single](https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode)). A message written while a turn runs is picked up *between tool calls inside the running turn*; several close-together messages can merge into one turn, and the `result` lists every uuid it consumed plus `queued_turn_count` for what is still waiting. `interrupt` returns a receipt `{still_queued:[uuid…]}` before the interrupted turn's `result` (capability `interrupt_receipt_v1`); with `cancel_queued:true` the queued messages are dropped instead of run next (`interrupt_cancel_queued_v1`) ([TS reference](https://code.claude.com/docs/en/agent-sdk/typescript)). Killing the process with SIGTERM leaves the turn unfinished (exit 143); SIGINT or `interrupt` ends it cleanly ([headless](https://code.claude.com/docs/en/headless)).

The interactive CLI has the same semantics a GUI copies ([interactive mode](https://code.claude.com/docs/en/interactive-mode)): Enter while working queues (shown grey); a queued *message* is handed to Claude as soon as the current tool calls finish, within the same turn; queued *commands* wait for the turn to end; `Esc` interrupts, keeps work done so far, and then sends what is queued; `Up` pulls queued items back into the editor.

**Sessions.** Transcripts live at `~/.claude/projects/<cwd with non-alphanumerics → '-'>/<session-id>.jsonl` (long names truncated and hashed), retained 30 days by default (`cleanupPeriodDays`) ([sessions](https://code.claude.com/docs/en/sessions)). Resume by id, `--continue` (latest in cwd), `--fork-session` (new id, copied history); `--resume` also accepts a `.jsonl` path and, in recent versions, finds an id in any project directory. The SDK now ships `listSessions()`, `getSessionMessages()`, `getSessionInfo()`, `renameSession()` and `tagSession()`, plus a pluggable `sessionStore` for resuming on another host ([SDK sessions](https://code.claude.com/docs/en/agent-sdk/sessions)) — so third-party clients no longer have to parse the JSONL themselves, though most still do.

**Policy constraint.** Third-party products built on the SDK may not offer claude.ai login or claude.ai rate limits ([overview](https://code.claude.com/docs/en/agent-sdk/overview)). This is why several clients (below) drive the user's own installed `claude` rather than a bundled one, and why Nimbalyst is adding a separate subscription-billed path that drives the interactive TUI.

## 2. Codex app-server (JSON-RPC)

OpenAI's equivalent is a long-lived **app-server** process speaking JSON-RPC 2.0 (the `"jsonrpc"` field omitted) ([docs](https://learn.chatgpt.com/docs/app-server), [repo](https://github.com/openai/codex/tree/main/codex-rs/app-server)).

- **Transports**: stdio JSONL (default, `--listen stdio://`), WebSocket `ws://IP:PORT` (experimental, one message per frame), Unix socket (WebSocket over HTTP Upgrade), or `off`.
- **Handshake**: exactly one `initialize` per connection, then an `initialized` notification; anything earlier gets "Not initialized".
- **Model**: Thread ⊃ Turn ⊃ Item. Threads: `thread/start`, `thread/resume`, `thread/fork` (optionally from `lastTurnId`), `thread/list` (filter by `archived`, `isPinned`, `cwd`, `searchTerm`), `thread/read`, `thread/archive` / `unarchive` / `delete`, `thread/unsubscribe`. Turns: `turn/start` (per-turn model, effort and sandbox overrides), `turn/steer`, `turn/interrupt`. Also `review/start`, `command/exec`, `model/list`, `account/read`.
- **Events**: `turn/started`, `turn/completed` (status `completed | interrupted | failed`), `turn/plan/updated`, `item/started`, `item/completed`, and deltas `item/agentMessage/delta`, `item/commandExecution/outputDelta`, `item/reasoning/textDelta`. Item types include `agentMessage`, `commandExecution`, `fileChange`, `mcpToolCall`, `webSearch`, `contextCompaction`, review-mode markers. A GUI renders by item type and replaces a card on `item/completed`.
- **Steer vs queue**: `turn/steer` appends input to the *active* turn, emits no new `turn/started`, and must carry `expectedTurnId` matching the active turn; it fails if no turn is running. Queueing a new turn after the current one is left to the client. `turn/interrupt` returns `{}` and the turn ends with `status: "interrupted"`.
- **Approvals** are server→client requests: `item/commandExecution/requestApproval` (decisions `accept | acceptForSession | decline | cancel | {acceptWithExecpolicyAmendment:…}`) and `item/fileChange/requestApproval` (`accept | acceptForSession | decline | cancel`), both carrying `threadId` and `turnId`; MCP elicitations arrive as `mcpServer/elicitation/request`. Whether they fire depends on the thread's approval policy and sandbox (`never`, `on-request`, … × `read-only`, `workspace-write`, `danger-full-access`).
- **Persistence**: threads are stored as JSONL rollout files on disk under Codex's session directory (`~/.codex/sessions/…`), which is why the desktop app "picks up your session history … from the Codex CLI and IDE extension" ([Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)).
- **Schema**: `codex app-server generate-ts` / `generate-json-schema` emit types matching the installed binary — the recommended way to avoid drift. An `experimentalApi` capability unlocks `process/spawn`, PTY resize, background terminals and paginated `thread/turns/list`.

Older or narrower modes: `codex exec --json` (non-interactive JSONL events, approvals fixed up front) and the `@openai/codex-sdk` TypeScript SDK (`thread.runStreamed`). Clients that need interactive approvals move off these onto app-server (cc-connect exposes this as `backend="app_server"`, see §9).

**Who uses it.** The Codex VS Code extension, the Codex desktop app, the TUI's `--remote` mode, and — notably — the new ACP adapter for Codex (§5). The Codex macOS app (launched 2026-02-02, [9to5Mac](https://9to5mac.com/2026/02/02/openai-launches-codex-app-for-macos-here-are-the-details/)) is a project/thread sidebar over app-server with built-in git worktrees per agent, inline diff review with comments, and "open in editor" ([OpenAI](https://openai.com/index/introducing-the-codex-app/)).

## 3. Anthropic's own GUIs: desktop app, claude.ai/code, Remote Control

- **Claude Code on the web** (launched 2025-10-20, [TechCrunch](https://techcrunch.com/2025/10/20/anthropic-brings-claude-code-to-the-web/)) runs each session in an Anthropic-managed VM (or a self-hosted runner); a proxy keeps git credentials outside the sandbox. The UI shows a `+42 −18` diff badge with inline line comments that ride along with the next message, a permission-mode dropdown, and *queued messages you can take back until Claude reads them* ([docs](https://code.claude.com/docs/en/claude-code-on-the-web)). `claude --cloud "task"` starts one from the terminal; `claude -p "msg" --cloud <id>` queues a follow-up and exits.
- **Teleport**: `claude --teleport [id]` / `/teleport` pulls a web session into the local CLI — checks the repo, requires a clean tree, fetches the session branch, loads full history; after that the two copies diverge (same doc).
- **Remote Control** (research preview 2026-02-24, [Help Net Security](https://www.helpnetsecurity.com/2026/02/25/anthropic-remote-control-claude-code-feature/)) is the canonical "mirror a local session to the phone" design ([docs](https://code.claude.com/docs/en/remote-control)). The local CLI makes outbound HTTPS only, registers with Anthropic's API, polls for work and streams over a long-lived connection; no inbound ports. Execution stays local; the transcript is stored server-side so devices stay in sync. Start it per session (`claude --rc`, `/remote-control`) or as a server (`claude remote-control --spawn same-dir|worktree|session --capacity N`). Pair by URL, QR code, or the session list in claude.ai/code and the mobile app's Code tab. Permission prompts and `AskUserQuestion` are forwarded and stay open until answered from any device; diffs are computed locally on demand; messages queue across network drops; push notifications fire. Limits: the local process must stay up; server mode gives up after ~10 min offline; API-key auth is not supported. A Remote Control interrupt from claude.ai cancels "the same way local Esc does" ([CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)).
- **Desktop app, Code tab** "runs the same underlying engine" as the CLI, keeps its own session list, lists CLI sessions under `/resume`, and accepts a CLI session via `/desktop` ([desktop docs](https://code.claude.com/docs/en/desktop)). Per-session opt-in git worktree under `<repo>/.claude/worktrees/`; parallel sessions with split view (redesigned 2026-04-14, [blog](https://claude.com/blog/claude-code-desktop-redesign)); diff viewer with line comments; mode selector Manual / Accept edits / Plan / Auto / Bypass; Local, Cloud and SSH sessions; "Continue in" pushes a local session to the cloud.

The notable design choice: the *mirror* is server-mediated (Anthropic relays and stores the transcript), while the *owner* of execution is always exactly one process — the local CLI or the cloud VM. Teleport and "Continue in" transfer ownership; they never make two processes drive the same session.

## 4. CodexMonitor

[Dimillian/CodexMonitor](https://github.com/Dimillian/CodexMonitor) (Tauri: Rust + React; macOS, Linux, Windows, iOS) is the reference third-party app-server client. Per its README it runs **one `codex app-server` over stdio per workspace**, renders reasoning and tool items as they stream, answers approval requests in-UI, shows staged/unstaged diffs, and supports resuming, pinning and archiving threads (all backed by app-server's thread methods, not its own DB). Worktrees and clones are created under the app's data directory. For iOS and headless machines it has an optional **remote daemon mode** that exposes the same JSON-RPC over the network, intended to be reached over Tailscale — i.e. the phone talks to the daemon, the daemon owns the app-server processes. Terminal and dictation are unavailable on mobile. Last push 2026-03-26. A smaller sibling, [rebornix/Agmente](https://github.com/rebornix/Agmente) (iOS, Swift), speaks both app-server and ACP.

## 5. Agent Client Protocol (ACP) and its clients

[ACP](https://agentclientprotocol.com) (spec repo [agentclientprotocol/agent-client-protocol](https://github.com/agentclientprotocol/agent-client-protocol), originated at Zed) is the LSP-style cross-vendor protocol: the client spawns the agent as a subprocess and speaks JSON-RPC 2.0 over stdio. Schema v1.23 / crate v1.9.1 as of 2026-09-18.

- **Agent-side methods** (v1 stable): `initialize`, `authenticate`, `session/new`, `session/load`, `session/resume`, `session/list`, `session/delete`, `session/close`, `session/set_mode`, `session/set_config_option`, `session/prompt`, `session/cancel`. Unstable: `session/fork`, `providers/*`, MCP-over-ACP (`mcp/connect|message|disconnect`), `document/did*`.
- **Client-side methods**: `session/update` (notification), `session/request_permission`, `fs/read_text_file`, `fs/write_text_file`, `terminal/create|output|wait_for_exit|kill|release`, `elicitation/*`.
- **Streaming**: `session/update` variants `user_message_chunk`, `agent_message_chunk`, `agent_thought_chunk`, `tool_call`, `tool_call_update`, `plan`, `available_commands_update`, `current_mode_update`, `config_option_update`, `session_info_update`, `usage_update`. A `tool_call` has a `ToolKind` (`read | edit | delete | move | search | execute | think | fetch | switch_mode | other`), status (`pending | in_progress | completed | failed`), content (text, diff with old/new text, or an embedded terminal) and file locations for "follow the agent".
- **Turn semantics**: `session/prompt` is a request whose *response* ends the turn with a `StopReason` (`end_turn | max_tokens | max_turn_requests | refusal | cancelled`). `session/cancel` is a notification; the agent must still answer the pending prompt with `cancelled`. There is no steer or queue primitive — sending during a turn is a client concern.
- **Permissions**: `session/request_permission` offers options of kind `allow_once | allow_always | reject_once | reject_always`.
- **v2 alpha** (2.0.0-alpha.5) renames auth methods and **drops `fs/*`, `terminal/*`, `session/load` and `session/set_mode`** — clients built on v1's client-side file and terminal callbacks should expect churn.

**Adapters for the two big agents** — both now sit on the vendors' own layers rather than scraping CLIs:
- [claude-agent-acp](https://github.com/agentclientprotocol/claude-agent-acp) (~2.6k★, formerly Zed's claude-code-acp) is built on the Claude Agent SDK; maps `canUseTool` to `request_permission`, supports images, @-mentions, edit review, TODO lists, background terminals, nested subagent transcripts. (The registry lists its license as "proprietary" while GitHub reports Apache-2.0 — check before depending on it.)
- [codex-acp](https://github.com/agentclientprotocol/codex-acp) (TS, new line; the Rust `zed-industries/codex-acp` is archived) "starts the Codex App Server, translates ACP requests into Codex operations, and maps Codex events back" — ACP layered on app-server.
- Native ACP agents: Gemini CLI, OpenCode (`opencode acp`), Cline (`cline --acp`), Kimi CLI (`kimi acp`, [docs](https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-acp.html)), Qwen Code (`qwen --acp`, [docs](https://github.com/QwenLM/qwen-code/blob/main/docs/users/integration-zed.md)).
- A [registry](https://github.com/agentclientprotocol/registry) (`<id>/agent.json` with an npx or binary distribution) lists ~45 agents; Zed installs from it (`zed: acp registry`) or takes custom `agent_servers` entries in settings ([Zed docs](https://zed.dev/docs/ai/external-agents)). External agents keep their own auth, billing, model choice and permissions.

**Clients** ([directory](https://agentclientprotocol.com/overview/clients), ~130 entries): Zed, JetBrains AI Assistant (`~/.jetbrains/acp.json`), Neovim (avante.nvim ~18k★, codecompanion.nvim ~6.9k★), Emacs (agent-shell), marimo, Toad (TUI), acpx (headless), DeepChat, plus IM bridges for Slack, Telegram, Discord, WeChat and Lark. `acp-mock` exists for testing clients without a live agent.

## 6. Orca (stablyai/orca)

[Orca](https://github.com/stablyai/orca) (~77k★, Electron, MIT) calls itself an "ADE" for fleets of parallel agents, and runs two driving modes side by side:

1. **PTY-first.** Any agent CLI runs in a node-pty terminal (WebGL renderer, restorable scrollback) inside its own git worktree. Working / done / waiting status comes from **managed hooks** Orca installs into each agent's config and receives on a local hook server (`src/main/agent-hooks/managed-hook-*.ts`, `src/relay/agent-hook-server.ts`). The optional "Chat UI" is "a structured transcript + composer for the same PTY": it tails and decodes the agent's own transcript files (Claude, Codex, Grok, OMP decoders in `src/main/native-chat/transcript-line-decoders-*.ts`) and types into the terminal ([native-chat docs](https://github.com/stablyai/orca/blob/main/docs/site/content/docs/agents/native-chat.mdx)).
2. **Structured sessions** "over the Codex app-server and the Claude Agent SDK" (`structured-agent-session-adapter.ts`). For Claude it uses the SDK with `pathToClaudeCodeExecutable` pointing at the user's own CLI and a custom spawn, `canUseTool` settled through a prompt registry. It has a real send-while-running queue: `cancelAsyncMessage(uuid)` withdraws a queued message "so an interrupted turn cannot spawn a later unexpected turn", and a journal/lease layer reports delivery as `unknown` rather than guessing after a crash.

Remote: a mobile companion pairs by one-time code over LAN or an "Orca Relay" (sign-in required), shows the Chat UI or raw terminal, answers prompts, gets push — "Desktop still owns the agent" ([mobile docs](https://github.com/stablyai/orca/blob/main/docs/site/content/docs/mobile.mdx)). Traffic is end-to-end encrypted with an app-layer keypair whose public key rides in the QR pairing offer, shared secret via ECDH (`src/main/runtime/e2ee-keypair.ts`). An SSH relay daemon covers remote machines.

## 7. AionUi (iOfficeAI/AionUi) — Chinese ecosystem

[AionUi](https://github.com/iOfficeAI/AionUi) (~33k★) is an Electron "cowork" GUI with a Rust backend, [AionCore](https://github.com/iOfficeAI/AionCore), fronting 20+ agents. The instructive part is its migration: it began as an ACP client for everything, then in v0.1.51 (2026-07-23) "route[d] claude/codex through the direct-CLI SessionAgentTask" — keeping ACP only for the long tail (Gemini, Qwen, others).

- Claude (`crates/aionui-session/src/backend/claude_conn.rs`): one long-lived stream-json process with the control protocol; always passes `--permission-mode`, sets the model in-band with `set_model` rather than `--model`; `can_use_tool` frames park in `pending_perms` and are answered by a keyed `control_response`; interrupt is written immediately, while queued control changes (mode, model) are drained last-write-wins at the start of the next send.
- Codex (`codex_conn.rs`): `codex app-server --stdio` with `thread/start|resume`, `turn/start`, `turn/interrupt`; approvals become generic Permission events; unsupported reverse-RPCs get `-32601`.
- Cancel emits a Finish event *before* tearing down the process tree, so the UI never waits on a dead process; a stale resume anchor falls back to a fresh session; idle sessions are released after 5 min.
- Remote: `--webui --remote` on port 3000 with username/password + JWT, for LAN; no tunnel or E2E encryption ([webui guide](https://github.com/iOfficeAI/AionUi/blob/main/docs/guides/webui.md)).

## 8. Vibe Kanban (BloopAI/vibe-kanban)

[Vibe Kanban](https://github.com/BloopAI/vibe-kanban) (~28k★, Rust + TS) treats each kanban card as a workspace with its own **git worktree, branch and dev server**. Bloop shut down on 2026-04-10; the project continues as fully local community open source ([blog](https://www.vibekanban.com/blog/shutdown)).

- Claude executor (`crates/executors/src/executors/claude.rs`): `npx -y @anthropic-ai/claude-code@<pinned> -p --output-format=stream-json --input-format=stream-json --verbose --include-partial-messages`; follow-ups use `--resume <id>`, optionally `--resume-session-at <uuid>` to truncate history (the basis of "edit an earlier message"). It registers a **PreToolUse hook** through `initialize` whose matcher excludes read-only tools (`^(?!(Glob|Grep|NotebookRead|Read|Task|TodoWrite)$).*`; in plan mode only `ExitPlanMode|AskUserQuestion`), returning `ask` to route those calls into `can_use_tool` → its approval service. Approval timeout returns `deny` with `interrupt:true`; a Stop hook checks for uncommitted changes.
- Codex executor: `npx -y @openai/codex@<pinned> app-server`, `thread/start`, `thread/fork` (for resume), `turn/start`; defaults `WorkspaceWrite` sandbox + `OnRequest` approvals routed to the same approval service.
- ACP executors drive Gemini and Qwen.
- Pinning exact agent versions via `npx` trades freshness for a stable wire.

## 9. cc-connect (chenhg5/cc-connect) — Chinese ecosystem, IM as the client

[cc-connect](https://github.com/chenhg5/cc-connect) (~16k★, Go) bridges 13 IM platforms (Feishu, DingTalk, WeCom, QQ, WeChat, Slack, Telegram, Discord, …) to local agents, mostly via outbound connections so no public IP is needed. It is the IM-side twin of a chat GUI and shows the same driver problems.

- Claude (`agent/claudecode/session.go`): one long-lived process per chat session with `--input-format stream-json --permission-prompt-tool stdio` and `--resume`. `can_use_tool` becomes a permission message to the IM user; the reply is written back as a `control_response`. Messages arriving while busy are written to stdin under a mutex and handled by Claude's own queue. Stop = close stdin → SIGTERM to the *process group* (5 s grace) → SIGKILL, so MCP grandchildren die too.
- Codex (`agent/codex/codex.go`): default `codex exec --json` (approvals fixed up front); `backend="app_server"` enables real approval requests.
- Chat commands `/new /list /switch /mode (yolo|default) /model /cron`; sessions rotate after 30 idle minutes; generic ACP and tmux backends exist.

## 10. Happy (slopus/happy) — mobile mirror with mode switching

[Happy](https://github.com/slopus/happy) (~24k★; CLI, relay server and Expo app now in one monorepo) solves "keep using the terminal, but answer from the phone" with a wrapper that **switches the owner of the session between two modes** (`packages/happy-cli/src/claude/loop.ts`):

- **Local mode** runs the real interactive `claude` TUI through a launcher that injects `--settings` with a SessionStart hook (to learn the session id), `--mcp-config` and `--append-system-prompt`, and patches `fetch` to report thinking state over fd 3. The phone is fed by tailing `<project dir>/<session>.jsonl` (`utils/sessionScanner.ts`): dedupe by uuid, drop `file-history-snapshot` / `queue-operation` lines, resync every 3 s.
- **Remote mode** starts when the phone sends a message or an abort/switch RPC: the local TUI is aborted and Happy runs the Agent SDK `query()` with a pushable async-iterable prompt, `--resume` on the *same* session id (so the conversation continues and still shows in `claude --resume`). Abort is an AbortController. Pressing a key locally switches back.
- **Permissions**: `canUseTool` writes the request into `agentState.requests[id]`, sends a push notification, and waits for the `permission` RPC; abort rejects everything pending; ExitPlanMode and AskUserQuestion are never auto-approved.
- **Relay**: the server only sees ciphertext — TweetNaCl box for key wrapping and AES-256-GCM with per-session data keys (`src/api/encryption.ts`).
- Codex is driven through app-server (`codex/codexAppServerClient.ts`) with thread fork and resume.

## 11. claudecodeui / CloudCLI (siteboon/claudecodeui)

[claudecodeui](https://github.com/siteboon/claudecodeui) (~14k★, AGPL-3.0, `npx @cloudcli-ai/cloudcli`) is a self-hosted Node server + PWA with user auth.
- Claude (`server/modules/providers/list/claude/claude-runtime.provider.js`): Agent SDK `query()`, resume via `resume` and `resumeSessionAt` (for editing a past message). `canUseTool` sends a `permission_request` over WebSocket and waits up to `CLAUDE_TOOL_APPROVAL_TIMEOUT_MS` (55 s) — except AskUserQuestion / ExitPlanMode, which wait indefinitely. Interrupt calls the SDK's `interrupt()`. A "held prompt stream" keeps stdin open after the last message so background tasks can finish.
- History is read straight from the JSONL files (including `subagents/agent-*.jsonl`), with only the path indexed in its own SQLite `sessions` table.
- Codex uses the Codex SDK `runStreamed` with the approval policy fixed up front (no interactive approvals).

## 12. opcode (winfunc/opcode, formerly Claudia)

[opcode](https://github.com/winfunc/opcode) (~22k★, Tauri) is the archetype of the *first-generation* design, useful mainly as a list of what later clients moved away from:
- **One `claude -p <prompt> --output-format stream-json --verbose --dangerously-skip-permissions` process per prompt**, `-c` or `--resume <id>` for follow-ups (`src-tauri/src/commands/claude.rs`). No approval UI at all.
- Queueing is client-only: prompts typed while a run is loading are held and sent on completion (`ClaudeCodeSession.tsx`). Stop kills the process (registry → child `kill()` → OS kill) and always emits `claude-cancelled`.
- Per-tool React widgets (Edit, MultiEdit, Bash, Grep, Task…) with diffs computed client-side from `old_string`/`new_string` (`ToolWidgets.tsx`).
- History is read directly from `~/.claude/projects/*/*.jsonl`; its own SQLite holds only agents and runs; "timeline" checkpoints are written under `~/.claude/projects/<proj>/.timelines/`.
- An optional axum web server binds `0.0.0.0` with a WebSocket for execution; no auth layer was found.

## 13. Conductor, Crystal/Nimbalyst, and smaller clients

- **Conductor** (Mac, closed source) is "built on Anthropic's Claude Agent SDK" ([changelog](https://www.conductor.build/changelog)) and also runs Codex, Cursor and OpenCode. Every workspace is a git worktree with per-workspace setup/run scripts and a `CONDUCTOR_PORT` ([workspaces](https://www.conductor.build/docs/concepts/workspaces-and-branches)). Message queue since 0.1.0 (2025-07); checkpoints 0.19.0; "steering" as a selectable follow-up behaviour in 0.50.0 (2026-05, [changelog](https://www.conductor.build/changelog/0.50.0-steering)); tool approval only as an opt-in enterprise setting (0.41.0), i.e. auto-run by default; Conductor Cloud microVMs with two-way local↔cloud sync (0.78.0, 2026-07).
- **Crystal** (~3.1k★, Electron) ran `claude --output-format stream-json` inside node-pty, one worktree per session, and in "approve" mode registered a stdio MCP server exposing `approve_permission`, passed as `--permission-prompt-tool mcp__crystal-permissions__approve_permission` and bridged over IPC to the UI (`mcpPermissionServer.ts`). Deprecated February 2026 in favour of **Nimbalyst** (~1.8k★), which moved to the Agent SDK with `canUseTool` for Claude and — tellingly — **ACP for Codex because "ACP exposes native pre/post file-edit hooks, which the Codex SDK does not"**, giving it pre-edit baselines for accurate diffs (`OpenAICodexACPProvider.ts`). Mobile sync is a zero-knowledge encrypted relay.
- **cui** (wbopan/cui, archived 2026-03) used the MCP permission-prompt-tool pattern and now points users at Anthropic's own web, Remote Control and Dispatch. **Omnara** pivoted away from wrapping local CLIs entirely.
- **desktop-cc-gui** (~4.4k★, Chinese, Tauri): one `claude -p` process per turn with `--permission-prompt-tool stdio`, but auto-*denies* every `can_use_tool` except AskUserQuestion ("headless -p cannot prompt mid-turn"), relying on `--allowedTools` pre-approval; Codex via app-server locally and `codex exec --json` for remote/WSL; Kimi and Grok via ACP.
- **codeg** (~3.7k★, Chinese, Tauri + Next.js): ACP-based, imports history from installed agents, one worktree per task, headless `codeg-server` with token auth and iOS/Android clients.

## 14. Cline and Roo Code (for contrast)

[Cline](https://github.com/cline/cline) (~69k★) runs its own agent loop against model APIs rather than driving an installed CLI; every edit and command asks for approval unless auto-approve is on (Plan → Act modes). It now ships a CLI that *is* an ACP agent (`cline --acp`), so GUIs drive Cline the same way they drive Gemini. Roo Code (~24k★) was shut down on 2026-05-15 and archived. Neither is a model for driving Claude Code or Codex; both are examples of the agent side of ACP.

---

## Summary comparison

| Product | Claude driver | Codex driver | Send during turn | Interrupt | Resume source | Permissions | Remote / mirror | Worktree |
|---|---|---|---|---|---|---|---|---|
| Claude desktop / web | own engine | — | queue, retractable | Esc semantics | own session store + CLI JSONL | mode selector + prompts | Remote Control relay (server-stored transcript) | opt-in |
| Codex app | — | app-server | `turn/steer` | `turn/interrupt` | rollout JSONL | approval requests | cloud tasks | built-in |
| Orca | PTY + transcript tail, or Agent SDK | PTY, or app-server | SDK queue with retract | SDK interrupt | agent's own files | hooks + `canUseTool` | E2E relay / LAN, desktop owns | yes |
| AionUi | long-lived stream-json + control | app-server | yes | control `interrupt` | agent's own | keyed `control_response` | LAN web + JWT | no |
| Vibe Kanban | stream-json + control + PreToolUse hook | app-server | follow-up via `--resume` | process | agent's own | approval service, timeout = deny+interrupt | tunnel / SSH | yes |
| Happy | TUI (local) ⇄ Agent SDK (remote) | app-server | yes (remote mode) | AbortController | CLI JSONL | `canUseTool` + push | E2E relay | — |
| cc-connect | long-lived stream-json + control | exec / app-server | written to stdin | process-group kill | agent's own | IM reply → `control_response` | IM platforms | — |
| claudecodeui | Agent SDK | Codex SDK | — | SDK interrupt | CLI JSONL | WebSocket, 55 s timeout | self-hosted web | — |
| opcode | `claude -p` per prompt | — | client-side hold | kill | CLI JSONL | skip-permissions | open web server | — |
| Zed + ACP | claude-agent-acp (SDK) | codex-acp (app-server) | client concern | `session/cancel` | `session/load` / `list` | `request_permission` | — | — |

## Patterns and trade-offs

**Convergence on two vendor wires, with ACP as the adapter layer above them.** The field has moved decisively off screen-scraping and off one-shot `claude -p` per turn. For Claude the wire is the stream-json control protocol (raw or via the Agent SDK); for Codex it is app-server JSON-RPC. ACP has not replaced these — its Claude and Codex adapters are thin translators *on top of* them. Clients that tried ACP-for-everything (AionUi) moved Claude and Codex back to the native wires to get features ACP lacks (in-band model switch, steer, fork, richer approval decisions), keeping ACP for the long tail where one integration buys twenty agents. The split runs the other way too: Nimbalyst chose ACP for Codex because ACP exposed file-edit hooks the Codex SDK did not.

**Long-lived process per conversation beats a process per turn.** Every first-generation client (opcode, Crystal, cui, desktop-cc-gui) spawned per turn and resumed by id; this makes mid-turn permission prompts impossible (desktop-cc-gui says so explicitly and auto-denies), makes queueing a client-side fiction, and pays startup cost per turn. Second-generation clients keep one process per live conversation and release it on idle (AionUi: 5 min).

**Three different "send while running" semantics.** Claude folds a queued message into the *running* turn at the next tool boundary (and can merge several); Codex separates `turn/steer` (into the running turn, must name `expectedTurnId`) from starting a new turn afterwards; ACP has neither and leaves it to the client. Good clients make the pending message visible and retractable (claude.ai/code, Orca's `cancelAsyncMessage`), and decide explicitly what interrupt does to the queue — Claude's default is "run the queue next", with an opt-in `cancel_queued`.

**Interrupt is a protocol message, not a signal.** Mature clients use `interrupt` / `turn/interrupt` / `session/cancel` and wait for the terminal event, falling back to process-group kill (cc-connect: close stdin → SIGTERM group → SIGKILL) only on timeout. Killing the child alone leaks MCP grandchildren; SIGTERM on Claude leaves the turn unfinished.

**The agent's own transcript is the durable record.** Almost nobody keeps an authoritative copy of the conversation outside the agent's files: clients read `~/.claude/projects/*.jsonl` and Codex rollouts, or use the new list/read APIs (`listSessions`, `thread/list`, `session/list`), and index only paths and titles. This gives free interop with the terminal (`claude --resume` sees GUI sessions and vice versa) at the cost of coupling to an undocumented, occasionally changing JSONL shape — and of 30-day retention unless configured.

**Permissions: four routes, one trend.** MCP `--permission-prompt-tool` (Crystal, cui) → stdio control `can_use_tool` (cc-connect, AionUi) → SDK `canUseTool` (Happy, claudecodeui, Orca) → hooks returning `ask` to scope which tools prompt (Vibe Kanban). Codex and ACP make approvals first-class server→client requests with "for this session" / "always" options. Where the user is remote, clients add push notifications and a timeout policy — and the policies differ (claudecodeui 55 s then deny; Vibe Kanban deny+interrupt; Remote Control waits until answered). A large share of clients simply run with skip-permissions or auto-run (opcode, Conductor by default, cc-connect's `yolo`), putting isolation into worktrees or sandboxes instead.

**Mirroring: one owner, many viewers.** Every multi-device design keeps a single process that executes (the local CLI, the desktop app, the daemon) and relays events to other devices: Remote Control (vendor server stores the transcript), Orca and Happy (E2E-encrypted relays that see only ciphertext), CodexMonitor (a daemon reached over Tailscale), AionUi (LAN web with JWT). Ownership transfer is explicit — teleport, "Continue in", Happy's local⇄remote switch — never two concurrent drivers of one session. Happy's trick of tailing the JSONL in local mode and taking over with `--resume` on the same id is the cheapest way to mirror a session that was started in a plain terminal.

**Worktree per conversation is standard for parallel agents** (Codex app, Claude desktop opt-in, Conductor, Crystal, Vibe Kanban, Orca, codeg), usually with per-worktree setup scripts and ports. Chat-first single-conversation clients (claudecodeui, AionUi, cc-connect) skip it.

## Worth borrowing / worth avoiding

**Borrow**
- Feature-detect from the handshake (`system/init.capabilities`, app-server `initialize`, ACP `initialize`) rather than parsing CLI versions.
- Correlate every user message with a client-generated uuid and use the agent's receipts (`user_message_uuids`, `still_queued`, `--replay-user-messages`) to show exactly which queued messages the agent has consumed.
- Make queued messages retractable until consumed, and decide explicitly whether interrupt runs or drops the queue.
- Treat pending permission requests as durable, re-deliverable state keyed by request id (the SDK re-delivers them on `reinitialize`); answering must be idempotent.
- Emit the UI's terminal event before tearing down a process tree (AionUi), and kill by process group.
- Report unknown delivery as unknown after a crash (Orca's journal) instead of re-sending and risking a duplicate turn.
- Use `codex app-server generate-ts` to generate types against the installed binary; pin agent versions only if you accept lagging features.
- For mirroring a terminal-started session, tail the agent's transcript and take over with resume-on-the-same-id rather than inventing a parallel session.
- End-to-end encrypt any relay that carries transcripts off the machine; put the public key in the pairing QR.

**Avoid**
- Spawning `claude -p` per turn when mid-turn approvals or queueing matter.
- Binding a control web server to `0.0.0.0` without auth (opcode).
- Scraping a TUI or PTY as the primary data source when a structured wire exists; keep PTY only as a fallback or for subscription-billed interactive use.
- Letting two processes drive the same session id concurrently; transfer ownership explicitly.
- Building heavily on ACP v1's client-side `fs/*` and `terminal/*` callbacks, which the v2 alpha removes.
- Offering claude.ai login inside a third-party product built on the Agent SDK — it is against Anthropic's terms; drive the user's own installed, logged-in CLI instead.
