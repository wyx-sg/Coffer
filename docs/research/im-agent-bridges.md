# IM agent bridges: how other products do it

**Feature**: driving a coding agent that runs on the owner's own machine from the chat apps they already use (Telegram, Slack, Feishu, SeaTalk, ...): inbound transport, sender access control, chat-to-session mapping, tool approvals, and rendering a long-running turn into chat · **Coffer spec**: [channels](../../openspec/specs/channels/spec.md) · **Related ADRs**: [channel-adapter-framework](../decisions/channel-adapter-framework.md), [channel-owner-gate](../decisions/channel-owner-gate.md), [channel-switches-structural-vs-parametric](../decisions/channel-switches-structural-vs-parametric.md), [channel-conversation-identity-and-context](../decisions/channel-conversation-identity-and-context.md), [channel-live-surface-strategy](../decisions/channel-live-surface-strategy.md), [channel-attachments](../decisions/channel-attachments.md), [telegram-long-polling](../decisions/telegram-long-polling.md), [seatalk-websocket-inbound](../decisions/seatalk-websocket-inbound.md), [driving-agents-through-sdk-and-app-server](../decisions/driving-agents-through-sdk-and-app-server.md), [managed-agents-run-with-full-permissions](../decisions/managed-agents-run-with-full-permissions.md)
**Researched**: 2026-09 · **Method**: web research and source reading of local clones, primary sources (official docs, repo source files, changelogs); stars checked 2026-09-24 via the GitHub API

## Scope and selection

Every bridge answers the same six questions:

1. **Agent drive**: how the bridge starts the agent, feeds it a turn, and reads events back.
2. **Inbound transport**: webhook, long polling, or a platform websocket/stream.
3. **Access control**: who may drive the agent, and how that list is built.
4. **Session mapping**: which chat, thread or topic maps to which agent session, working directory and model.
5. **Approvals**: how a tool-permission prompt reaches a phone and how the answer gets back.
6. **Rendering**: streaming, chunking, markdown conversion, status, attachments and voice.

Hosted "omnichannel bot" platforms (Azure Bot Service, Twilio Conversations, Botpress, Rasa, Chatwoot) are left out: they host a bot, they do not bridge to an agent on the user's machine. Products, by adoption as of 2026-09:

| Product | Class | Stars / reach | Latest activity |
| --- | --- | --- | --- |
| OpenClaw | Personal assistant with a multi-channel gateway | 390k | active |
| Hermes Agent (Nous Research) | Agent with a messaging gateway | 249k | active |
| Claude Code Channels (claude-plugins-official) | First-party MCP channel plugins | 36.7k (plugin repo) | research preview |
| Happy | Mobile/web client for Claude Code and Codex, E2E-encrypted relay | 23.9k | 2026-09-22 |
| cc-connect | Local agents to 15+ chat platforms (Chinese ecosystem) | 15.7k | v1.5.1-beta.1, 2026-08-28 |
| claude-code-telegram | Telegram bot on the Claude Agent SDK | 2.8k | v1.8.0, 2026-09-22 |
| OpenAB / OpenACP | ACP-based chat bridges | 805 / 426 | 2026 |
| ccgram (alexei-led) | Telegram topics to tmux-hosted agents | 269 | v4.12.2, 2026-09-23 |
| Claude Code Remote Control / Codex Remote | First-party phone steering of a local session | bundled | GA / rollout |
| Claude Code in Slack / Codex in Slack | First-party ChatOps, runs in the cloud | bundled | GA |

Omnara (2.9k), once a phone client for Claude Code, relaunched on 2026-09-02 as an open-source managed-agents platform and no longer wraps a local agent ([changelog](https://github.com/omnara-ai/omnara/blob/main/docs/changelog.mdx)); it is covered only for its permission model. jsayubi/ccgram (27 stars, last release 2026-04) is a smaller, hook-driven project of the same name, covered briefly for its hook-based approval design.

## First-party mechanisms

### Claude Code Channels

A channel is an MCP server that pushes events into a Claude Code session that is already running ([channels](https://code.claude.com/docs/en/channels), [channels reference](https://code.claude.com/docs/en/channels-reference)). It is a research preview; the flag and protocol "may change".

- **Activation.** The session must be launched with `claude --channels plugin:telegram@claude-plugins-official`; listing the server in `.mcp.json` is not enough. Local development uses `--dangerously-load-development-channels server:<name>`.
- **Capability declaration.** The server declares `capabilities.experimental['claude/channel']: {}`; a two-way channel also declares `tools: {}` and exposes a reply tool. Declaring `experimental['claude/channel/permission']: {}` opts into permission relay and asserts that the server authenticates whoever answers.
- **Inbound.** The server sends the MCP notification `notifications/claude/channel` with `{content, meta}`. `meta` keys may only contain letters, digits and underscores; other keys are silently dropped. The model sees the event as a `channel` tag carrying `source`, `chat_id` and the other meta attributes. Events arrive only while the session is open.
- **Permission relay.** Claude Code sends `notifications/claude/channel/permission_request` with `{request_id, tool_name, description, input_preview}`; the server answers `notifications/claude/channel/permission` with `{request_id, behavior: 'allow'|'deny'}`. `request_id` is five lowercase letters excluding `l`, so it can be typed on a phone. The terminal dialog stays open in parallel and the first answer wins. Only tool approvals are relayed, not project-trust or MCP-consent prompts. Previews are sanitised and credentials masked from v2.1.234.
- **Enterprise controls.** `channelsEnabled` is the master switch (off by default on Team and Enterprise) and `allowedChannelPlugins: [{marketplace, plugin}]` replaces Anthropic's allowlist.

The official plugins ([claude-plugins-official/external_plugins](https://github.com/anthropics/claude-plugins-official/tree/main/external_plugins)) are Bun stdio MCP servers for Telegram, Discord and iMessage, plus a `fakechat` localhost demo:

- **Transport.** Telegram uses grammY long polling with no webhook; since a token allows one poller, it writes `bot.pid`, kills a stale holder and retries 409 Conflict with backoff up to 8 attempts ([telegram/server.ts](https://github.com/anthropics/claude-plugins-official/blob/main/external_plugins/telegram/server.ts)). Discord uses the discord.js gateway websocket. iMessage polls `~/Library/Messages/chat.db` every second from a ROWID watermark and sends through `osascript`.
- **Access file.** `~/.claude/channels/<name>/access.json` holds `dmPolicy: 'pairing'|'allowlist'|'disabled'`, `allowFrom: string[]`, `groups: {[id]: {requireMention (default true), allowFrom}}`, `pending: {[code]: {senderId, chatId, createdAt, expiresAt, replies}}`, `mentionPatterns`, `replyToMode`, `textChunkLimit`, `chunkMode`. It is re-read on every inbound message, written atomically with mode 0600, and a corrupt file is renamed aside rather than trusted.
- **Pairing.** A stranger's DM gets a 6-hex-character code (1-hour TTL, at most 3 pending, at most 2 replies per sender, then silence). The owner approves in the terminal with `/telegram:access pair <code>`; the skill drops a file under `approved/`, which the server polls every 5 s to send "Paired!". The docs recommend switching to `allowlist` afterwards so strangers get no reply at all, and gating on the sender (`message.from.id`), not the chat. iMessage defaults to `allowlist` so pairing codes are not auto-sent to friends.
- **Prompt-injection guards.** The server `instructions` tell the model to refuse access changes requested from inside a channel message. Attachment metadata travels only in `meta`, never in the content text, because a sender could forge text; uploader-controlled names are sanitised.
- **Reply tools.** Telegram exposes `reply` (files up to 50 MB, text or MarkdownV2), `react`, `edit_message` and `download_attachment`; the model is told that edits do not push-notify, so a finished task needs a fresh reply. Discord adds `fetch_messages` because bots have no search API. Every outbound tool checks `assertAllowedChat`.
- **Approval UI.** Telegram and Discord DM each allowlisted user a `Permission: <tool>` message with Allow / Deny / See more buttons (`perm:allow:<id>`); a typed `yes abcde` also works, matched by `/^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$/i`. iMessage sends the prompt only to the owner's self-chat.

### Claude Code Remote Control

Remote Control makes a local interactive session reachable from claude.ai/code and the Claude mobile app ([remote-control](https://code.claude.com/docs/en/remote-control)).

- **Transport.** The local process "makes outbound HTTPS requests only and never opens inbound ports": it registers with the Anthropic API, polls for work, and switches to a streaming connection when a device attaches. The transcript is held on Anthropic's servers while connected; execution and file access stay local.
- **Entry points.** `claude remote-control` (server mode, prints a URL and a QR code), `claude --remote-control`/`--rc`, or `/remote-control` inside a running session.
- **Concurrency.** `--spawn same-dir|worktree|session`; `worktree` gives each phone-started session its own git worktree; `--capacity` defaults to 32.
- **Phone surface.** Messages, image and file attachments, `@` file autocomplete, git diff, and a subset of slash commands (`/model`, `/effort`, `/compact`, ...).
- **Failure handling.** Sessions resume for about 4 hours after the server stops; server mode exits after about a 10-minute network outage; heartbeat loss for about 30 minutes disconnects. Pro/Max/Team/Enterprise only, not API keys.

### Claude Code in Slack and Codex in Slack

Both run in the vendor's cloud, not on the user's machine, and are included as the reference for thread-scoped ChatOps.

- **Claude Code in Slack** ([slack](https://code.claude.com/docs/en/slack)): an `@Claude` mention in a channel (not DMs) opens a cloud session under the mentioning user's own account. It reads the whole thread when mentioned in one, picks a repository from context with a "Change Repo" button, posts status to the thread, and ends with **View Session** and **Create PR** buttons. Routing is "Code only" or "Code + Chat" with intent detection and a "Retry as Code" fallback. Being retired for Team and Enterprise in favour of Claude Tag.
- **Codex in Slack** ([docs](https://learn.chatgpt.com/docs/third-party/slack)): `@Codex` creates a cloud task in the best-matching environment, uses thread context, reacts with an emoji to acknowledge, and posts a link plus results; admins can restrict it to posting only the link.

### Codex Remote and the Codex app-server

- **Codex Remote** ([docs](https://learn.chatgpt.com/docs/remote)): the ChatGPT mobile app steers tasks on a paired Mac or PC (desktop app, Settings → Connections, scan a QR code). A vendor relay keeps the machine reachable without exposing it; the host must stay awake and signed in. The phone can start tasks, approve requests and review diffs, test results and screenshots.
- **App-server approvals** ([app-server](https://learn.chatgpt.com/docs/app-server)): the approval surface any third-party bridge uses. `codex app-server` speaks JSON-RPC 2.0 over stdio (or websocket). Approvals are server-to-client requests: `item/commandExecution/requestApproval` (with `command`, `cwd`, `reason`, `availableDecisions`) and `item/fileChange/requestApproval` (with `grantRoot`), answered `accept | acceptForSession | decline | cancel`; commands also accept an exec-policy amendment. The sequence is `item/started` → request → reply → `serverRequest/resolved` → `item/completed` with `declined` when refused. `item/permissions/requestApproval` grants a subset of permissions for `turn` or `session`; `tool/requestUserInput` asks 1–3 questions with an `autoResolutionMs` timeout. `codex exec --json` emits events only and cannot carry an approval back, and `codex mcp-server` has been removed in favour of the app-server ([removal note](https://learn.chatgpt.com/docs/mcp-server)).

## Open-source bridges

### OpenClaw

OpenClaw is a personal assistant whose Gateway is "a single long-lived daemon" that owns every messaging surface: WhatsApp (Baileys), Telegram (grammY), Slack, Discord, Signal, iMessage, Teams, Google Chat, WebChat and 20+ more through plugins ([architecture](https://docs.openclaw.ai/concepts/architecture)).

- **Control plane.** The Gateway binds `127.0.0.1:18789`; the macOS app, CLI and web UI connect over WebSocket as control clients, and devices as `role: node`. New devices pair and receive a device token; loopback can be auto-approved, LAN and tailnet cannot. Side-effecting methods (`send`, `agent`) require idempotency keys.
- **DM pairing** ([pairing](https://docs.openclaw.ai/channels/pairing)). `dmPolicy: "pairing"` is the default: an unknown sender gets an 8-character uppercase code with no ambiguous characters, valid for 1 hour, at most 3 pending per account, approved with `openclaw pairing approve <channel> <CODE>`. `"open"` is public only if the allowlist contains `"*"`. Groups have a separate `groupPolicy` / `groupAllowFrom`.
- **Session routing** ([session](https://docs.openclaw.ai/concepts/session)). `session.dmScope` is `main` (every DM shares one session), `per-peer`, `per-channel-peer` (recommended) or `per-account-channel-peer`; `groupScope` is `per-group` or `main`; `session.reset.mode` is `none`, `daily` or `idle`. Multi-agent routing uses `bindings` of `agentId` plus a `match` rule.
- **External coding agents** ([ACP agents](https://docs.openclaw.ai/tools/acp-agents)). The `acpx` runtime plugin spawns Claude Code, Codex, Cursor, Gemini CLI and others over ACP with `/acp spawn ... --thread auto|here|off`, binding the child session to a chat thread.

### Hermes Agent

Hermes' gateway is one background process connected to 30+ platforms (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Feishu, WeCom, Teams, ...) with a per-chat session store ([messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging)). Users are denied by default unless listed (`TELEGRAM_ALLOWED_USERS`) or paired (`hermes pairing approve`). Dangerous commands wait for `/approve` or `/deny` in chat. Outbound delivery goes through a durable ledger with at-least-once semantics.

### cc-connect

cc-connect ([repo](https://github.com/chenhg5/cc-connect)) is a Go daemon that bridges a local agent to 15+ platforms and is the reference for the Chinese ecosystem.

- **Agent drive.** Agents are plugins registered with `core.RegisterAgent`. Claude Code runs as a long-lived subprocess, `claude --output-format stream-json --input-format stream-json --permission-prompt-tool stdio [--resume <sid>] [--permission-mode M] [--model] [--effort]`: turns are JSON lines on stdin (images as base64 blocks) and events are read from stdout ([agent/claudecode/session.go](https://github.com/chenhg5/cc-connect/blob/main/agent/claudecode/session.go)). Codex has two backends, `codex exec --json` (no approval path) and `codex app-server` over JSON-RPC ([agent/codex/appserver_session.go](https://github.com/chenhg5/cc-connect/blob/main/agent/codex/appserver_session.go)). A generic ACP client covers Devin and other ACP agents; a tmux agent sends keys and polls `capture-pane` for anything else.
- **Transport per platform** ([README](https://github.com/chenhg5/cc-connect/blob/main/README.md)): Feishu/Lark, WeCom, WPS, Weibo, QQ over websocket; DingTalk Stream mode; Slack Socket Mode; Discord gateway; Telegram and personal WeChat long polling; Matrix `/sync`; Google Chat via Pub/Sub; LINE by webhook (the only one needing a public URL). Most platforms need no inbound port.
- **Session mapping.** The key is `platform:chat[:thread]:user`, or `platform:chat[:thread]` when `share_session_in_channel` is set; `session_scope` picks user / channel / thread. Each key has an active session plus past ones, persisted as JSON under `sessions/<project>_<hash(workdir)>.json` ([core/session.go](https://github.com/chenhg5/cc-connect/blob/main/core/session.go)). The agent's session id is saved from the result event and passed as `--resume` next turn. `[[projects]]` bind agent + work_dir + platforms; a multi-workspace mode adds `/workspace`, `/bind`, `/dir` with idle eviction.
- **Access.** Per-platform `allow_from` (IDs or `"*"`, the default) and `admin_from` for privileged commands; `/whoami` prints an ID to paste. Groups need an @mention or a reply to the bot unless `group_reply_all`. No pairing.
- **Approvals.** A `control_request` of subtype `can_use_tool` first passes auto-allow/deny rules by mode, then Claude's own `PermissionRequest` hooks, then reaches chat as "Allow / Deny / Allow all" inline buttons, or cards on Feishu, DingTalk and Slack; a multilingual keyword fallback matches typed replies ("允许", "allow all"). There is no timeout: the engine blocks until answered and pauses the idle timer ([core/engine.go](https://github.com/chenhg5/cc-connect/blob/main/core/engine.go)).
- **Rendering.** Streaming preview by editing a message (1.5 s interval, 30-character minimum delta, 2000-character preview cap), tool-step progress cards, markdown to Telegram HTML or Slack mrkdwn with a plain-text fallback when parsing fails, typing ticker, speech-to-text and text-to-speech.
- **Operations.** A 40+ command set (`/new /list /switch /model /mode /provider /cron /timer /stop /diff /btw ...`), cron with `jobs.json`, bot-to-bot relay, an inbound webhook trigger, 60 s message dedup, inbound and outbound rate limiting, self-healing of stale busy locks after restart, and a web admin UI.

### Happy

Happy ([repo](https://github.com/slopus/happy)) is a CLI wrapper plus an Expo mobile/web app and a relay server, all open source and self-hostable.

- **Local/remote mode switch.** `happy` runs the real Claude Code CLI with the user's terminal inherited (no PTY emulation) and mirrors the conversation by tailing Claude's JSONL transcript; a generated `SessionStart` hook reports the session id ([claude/loop.ts](https://github.com/slopus/happy/blob/main/packages/happy-cli/src/claude/loop.ts)). When a message arrives from the phone, the local process is killed and the loop switches to remote mode, which drives the same session through the Claude Agent SDK `query()` with `resume: sessionId`. A keypress in the terminal switches back. Codex is driven through a hand-written JSON-RPC client for `codex app-server`, chosen because the Codex SDK only wraps `codex exec` and has no approval callback ([codexAppServerClient.ts](https://github.com/slopus/happy/blob/main/packages/happy-cli/src/codex/codexAppServerClient.ts)).
- **Relay.** Fastify plus Socket.IO with Postgres and Redis. Sockets are user-, session- or machine-scoped; durable updates carry a per-user `seq` for reconnect reconciliation; metadata writes use `expectedVersion` for optimistic concurrency; RPC (`rpc-register` / `rpc-call`) lets the phone call handlers on the machine, including `spawn-session` on a daemon ([docs/protocol.md](https://github.com/slopus/happy/blob/main/docs/protocol.md)).
- **End-to-end encryption** ([docs/encryption.md](https://github.com/slopus/happy/blob/main/docs/encryption.md)). Pairing is a QR code carrying the CLI's ephemeral NaCl box public key; the phone returns the account key box-encrypted to it. Content uses AES-256-GCM under per-session data keys wrapped with NaCl box. The server sees ids, sequence numbers, timestamps, push tokens and the permission mode, but not messages, metadata or agent state.
- **Approvals and push.** The SDK `canUseTool` callback records a pending request in encrypted agent state and sends an Expo push ("Permission request"); the phone answers by RPC with `{id, approved, mode?, allowTools?, updatedInput?}`. Push kinds are `done`, `permission` and `question`.
- **Voice.** An ElevenLabs conversational agent in the app, with client tools that message the session and answer permission requests.

### claude-code-telegram

claude-code-telegram ([repo](https://github.com/RichardAtCT/claude-code-telegram)) is a Python Telegram bot on the Claude Agent SDK.

- **Agent drive.** `ClaudeSDKClient` with `cwd`, allowed/disallowed tools, `max_budget_usd`, a sandbox block, `setting_sources=["project"]`, `can_use_tool` and `resume` ([src/claude/sdk_integration.py](https://github.com/RichardAtCT/claude-code-telegram/blob/main/src/claude/sdk_integration.py)). Auto-resume picks the latest unexpired session for the same user and directory and retries fresh if resume fails.
- **Sessions.** Optional project threads map Telegram forum topics to projects from a YAML registry, keyed `chat_id:thread_id`; `/cd` and `/repo` stay inside `APPROVED_DIRECTORY`. SQLite holds sessions, messages, tool usage, audit log, cost tracking and scheduled jobs.
- **Access.** `ALLOWED_USERS` and/or token auth, a security middleware, and an audit log. No pairing.
- **Approvals.** `can_use_tool` first denies paths outside the working directory and directory-escaping bash, then, when interactive approval is on, forces Bash / Write / Edit through Allow/Deny buttons by removing them from `allowed_tools`. The wait has a 60 s timeout with a configurable default action (`deny` unless set to `allow`), and the prompt is edited to "Timed out".
- **Rendering.** A progress message edited in place with tool names and a Stop button; `sendMessageDraft` streaming in private chats; HTML output split at about 4000 characters with code-block-aware chunking; voice transcription; image extraction from output.
- **Triggers.** GitHub and generic webhooks (HMAC or shared secret, deduplicated by delivery id) and APScheduler cron jobs publish events that start agent runs.

### ccgram (alexei-led)

ccgram ([repo](https://github.com/alexei-led/ccgram)) drives agents that live in a terminal multiplexer, so the terminal session and the chat stay two views of the same process.

- **Agent drive.** Input goes in with tmux `send-keys` (or the herdr / agterm backends). Output is read from the agent's transcript JSONL, polled every second, plus pane capture parsed with `pyte` ([docs/architecture.md](https://github.com/alexei-led/ccgram/blob/main/docs/architecture.md)). Installed hooks (SessionStart, Stop, Notification, ...) write `session_map.json` and an `events.jsonl`. Claude, Codex, Gemini, Pi and a plain shell are supported.
- **Mapping.** One Telegram forum topic = one multiplexer window = one agent session. Opening a new topic starts a directory browser, then an agent picker, then launches the window, optionally in a git worktree. After a restart, a banner offers Resume / Continue / Fresh.
- **Approvals.** No SDK callback: permission prompts, `AskUserQuestion` and plan-mode exits are detected by regex on the captured pane and rendered as inline keyboards that send arrow keys, Enter or Escape back to the pane. A prompt left unanswered simply stays in the terminal.
- **Rendering.** At-least-once delivery from the transcript through a queue that merges consecutive text and offers "Jump to live" when the backlog exceeds 100 items or 5 minutes; `sendMessageDraft` streaming with send-and-edit fallback; a single editable status bubble; topic emoji as status; live terminal screenshots; voice via Whisper.
- **Access.** Required `ALLOWED_USERS`; in a group the bot must be an admin. No pairing.

The unrelated jsayubi/ccgram ([repo](https://github.com/jsayubi/ccgram)) shows the hook-only variant: a `PermissionRequest` hook sends Allow / Deny / Always / Defer buttons and polls for a response file for 90 s; on timeout it prints nothing so Claude falls back to its terminal prompt. It also suppresses notifications while the user has typed in the terminal within the last 5 minutes.

### ACP bridges: OpenACP and OpenAB

Both put the Agent Client Protocol between the chat and the agent, so one bridge covers every ACP-speaking CLI.

- **OpenACP** ([site](https://openacp.ai/), [repo](https://github.com/Open-ACP/OpenACP)): Telegram (a forum topic per session), Discord (a thread per session) and Slack (Socket Mode, a thread per session) to "28+ agents from the ACP Registry"; approvals in chat; "no cloud relay".
- **OpenAB** ([repo](https://github.com/openabdev/openab)): Rust, Discord and Slack natively, other platforms through a custom gateway; "one CLI process per thread" with `max_sessions = 10` and `session_ttl_hours = 24`; access via `allowed_channels` and `allowed_users`; deployed on Kubernetes.

### Omnara's permission model

After its pivot, Omnara runs its own agent harness instead of wrapping Claude Code, but its permission and input model is a clean reference ([permissions](https://github.com/omnara-ai/omnara/blob/main/docs/tools/permissions.mdx), [interactions](https://github.com/omnara-ai/omnara/blob/main/docs/events/interactions.mdx), [sending input](https://github.com/omnara-ai/omnara/blob/main/docs/events/sending-input.mdx)). Each tool is `always_allow | always_ask | always_deny`, with MCP tools defaulting to `always_ask`. An ask puts the tool call in `awaiting_permission` and opens an interaction (`open | resolved | canceled`) whose form always has Allow at index 0 and Deny at index 1; Deny accepts free text that the model sees as the reason. User input is stored first and appended to the timeline, with `input_kind` of `content`, `interaction_response`, `control` or `config_change`, and a busy agent accepts input without being interrupted. Its Slack integration launches one agent per thread or DM.

## Summary table

| | Agent drive | Transport | Access | Session key | Approval path | Streaming |
| --- | --- | --- | --- | --- | --- | --- |
| Claude Code Channels | MCP push into a live session | long poll / gateway / chat.db poll | pairing → allowlist, per sender | the one open session | `permission_request` notification, 5-letter id | model calls `edit_message` |
| Remote Control | first-party | outbound HTTPS poll + stream | account | session URL | native UI | native |
| OpenClaw | own agent; ACP for coding CLIs | per-platform, one gateway | pairing (8 chars, 1 h) | `dmScope` / `groupScope` | per agent | per platform |
| cc-connect | stream-json stdin/stdout; app-server; ACP; tmux | mostly websocket / stream mode | `allow_from`, mention in groups | `platform:chat[:thread]:user` | `--permission-prompt-tool stdio`, buttons/cards, no timeout | edit, 1.5 s |
| Happy | local CLI ↔ Agent SDK switch; app-server | own E2E relay | QR key exchange | one session per CLI | `canUseTool` + push + RPC | app |
| claude-code-telegram | Agent SDK | long poll or webhook | allowlist / token | user + directory, or topic | `can_use_tool`, 60 s, default deny | draft + edit |
| ccgram | tmux keys + transcript tail | long poll | allowlist | forum topic ↔ window | pane regex → keypresses | draft + edit |
| OpenACP / OpenAB | ACP | Telegram / Discord / Slack | allowlist | thread per session | ACP permission | per platform |

## Patterns and trade-offs

- **Agent drive splits three ways.** (1) A structured bidirectional protocol: Agent SDK `canUseTool`, `--input-format stream-json` with `--permission-prompt-tool stdio`, Codex app-server, or ACP. (2) Terminal puppeting: tmux keys in, transcript JSONL or pane capture out. (3) Injecting into a session the user already has open (Channels, Remote Control, Happy's local mode). Structured protocols give typed approvals and clean events; puppeting keeps the terminal and the chat as one process the user can walk up to, at the cost of regex-parsing prompts. One-way modes (`claude -p` stdout, `codex exec --json`) cannot carry an approval back, and every bridge that needed approvals moved off them.
- **Outbound-only transports win.** Long polling, Slack Socket Mode, Discord's gateway, Feishu and WeCom websockets, DingTalk Stream mode, and Remote Control's HTTPS polling all avoid a public URL; webhooks survive only where a platform offers nothing else (LINE) or as an opt-in. Long polling needs single-poller discipline: one poller per token, a pid file, and backoff on 409 Conflict.
- **Access converges on sender identity, not chat identity.** Channels, OpenClaw and Hermes pair unknown senders with a short-lived code (6–8 characters, 1 hour, 3 pending) approved from the trusted side, then drop to an allowlist with silent ignore. Simpler bridges use a static ID allowlist and print the ID with `/whoami`. Groups are gated separately, usually with a mention requirement.
- **Session scope is a configuration axis.** OpenClaw's `dmScope`, cc-connect's `session_scope` and `share_session_in_channel`, and thread- or topic-per-session in ccgram, OpenACP, OpenAB and both Slack integrations all say the same thing: the key is some prefix of (platform, account, chat, thread, user), and the right prefix depends on whether a group is one conversation or many. Forum topics and Slack threads are the favoured unit for running several sessions side by side.
- **Approvals split on timeout policy.** cc-connect blocks indefinitely and pauses its idle timer; claude-code-telegram times out after 60 s to a configurable default; jsayubi/ccgram times out and falls back to the terminal; Channels keeps the terminal dialog open in parallel and takes the first answer. Short, typeable request ids (Channels) make text replies work where buttons are unavailable.
- **Rendering is edit-in-place plus a final message.** Bridges stream by editing one message on an interval with a minimum delta, or with Telegram's `sendMessageDraft`, then send the final answer as new, chunked messages converted to the platform's markup, with a plain-text fallback. Because edits do not notify, completion is signalled with a fresh message. Tool steps collapse into one status message or card.

## Worth borrowing / worth avoiding

**Borrow**

- A tiny, typeable approval id (Channels' five letters without `l`) alongside buttons, so approvals work on platforms without interactive messages.
- Attachment and sender metadata carried in structured fields, never in text the model reads as content, and access changes refused when requested from inside a chat message (Channels).
- Pairing codes with a short TTL, a cap on pending codes and a cap on replies per stranger, followed by silence (Channels, OpenClaw).
- Session scope as a named, documented setting with a recommended default (OpenClaw's `per-channel-peer`) rather than an implicit rule.
- Saving the agent's own session id from each result and resuming with it, with a fresh-session fallback when resume fails (cc-connect, claude-code-telegram).
- At-least-once delivery from a transcript with backlog merging and a "jump to live" escape (ccgram), and a durable delivery ledger (Hermes), so a restart does not drop a finished answer.
- Pausing idle timers while waiting on a human (cc-connect), and a completion message that is new rather than edited.
- Platform capability flags (buttons, cards, edits, drafts) with text fallbacks, as cc-connect's per-platform senders do.

**Avoid**

- One-way agent modes for anything that must receive a decision from chat.
- Parsing terminal panes for prompts unless keeping the terminal as the source of truth is the point; the regexes break with every agent UI change.
- Keying access on the chat instead of the sender, which lets any group member drive the agent.
- An open-by-default allowlist (`"*"` as default); pairing or deny-by-default is the safer baseline.
- Approval waits with no bound and no visible state, or timeouts that silently allow.
- Webhooks as the default transport for a program on a laptop.
