# Coffer Drives Claude Code Through the Agent SDK and Codex Through `codex app-server`

**Status**: Accepted
**Date**: 2026-06-21
**Deciders**: Yuxing Wu
**Related**: [Coffer Model Is an Internal Engine](coffer-model-is-an-internal-engine.md); spec chat ("Ship Claude Code and Codex subprocess providers", "Keep each agent adapter self-contained", "End every adapter stream with a terminal event", "Retry a forgotten resume id once as a fresh session", "Express a turn as typed events");
[Managed Agents Run With Full Permissions](managed-agents-run-with-full-permissions.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md),
[Channel Attachments](channel-attachments.md), [Channel Live Surface Strategy](channel-live-surface-strategy.md),
[Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md), [Session Subprocess Model](session-subprocess-model.md);
research note [Agent chat clients](../research/agent-chat-clients.md); PRs #77, #82, #101, #146

## Context

Coffer's chat platform — the web Chat page and every channel — runs turns on
the user's own coding agents, Claude Code and Codex, rather than on a model of
its own ([Coffer Model Is an Internal Engine](coffer-model-is-an-internal-engine.md)).
The agent must run as the user runs it: same CLI, same login, same config
directory (skills, MCP entry, instructions), same tools. What Coffer needs
from the integration, per turn:

- **A stream of typed events** — text increments as they are written (a
  channel's live surface grows from them), tool calls and results, a terminal
  event with usage — mapped onto the platform's `AgentEvent`s.
- **Interrupt** that stops the turn cleanly and leaves the session resumable,
  because the owner presses stop from a phone or the web page.
- **Session continuity** across turns and daemon restarts: the upstream
  session id is stored as `AgentConfig.session_id` and resumed next turn; a
  forgotten id is retried once as a fresh session.
- **Per-turn parameters**: model and reasoning effort, an appended system
  context ("you are on a chat channel"), the working directory, environment
  (the agent's config directory), and inline images for Claude.
- **Full permissions** with no interactive prompt, since nobody is at the
  terminal ([Managed Agents Run With Full
  Permissions](managed-agents-run-with-full-permissions.md)).

## Options Considered

### Option A — Claude Code via the Python Claude Agent SDK's `ClaudeSDKClient`; Codex via the `codex app-server` JSON-RPC protocol (chosen)

**Claude Code.** `infrastructure/chat/claude_sdk_agent.py` builds a
`ClaudeSDKClient` per turn with `ClaudeAgentOptions`: `cwd`,
`resume=<session_id>`, `permission_mode="bypassPermissions"`, `model`,
`effort`, `include_partial_messages=True` (without it the SDK yields only whole
assistant messages and a live surface has nothing to grow), the preset
`claude_code` system prompt with Coffer's context appended rather than
replacing it, and `env`. The turn's content goes in as streamed input, so a
turn with attachments is a list of text and base64 `image` blocks. Interrupt is
the client's own `interrupt()`. The SDK bundles and prefers its own Claude Code
binary. The dependency (`claude-agent-sdk>=0.2,<0.3`) is confined by
import-linter to `infrastructure/chat`.

**Codex.** `infrastructure/chat/codex_agent.py` spawns `codex app-server` for
the turn (`codex_app_server.py`, as a tracked child process so a daemon crash
leaves no orphan) and speaks JSON-RPC 2.0 over stdio, NDJSON-framed, through a
stdlib-only client (`codex_jsonrpc.py`): `initialize` → `thread/resume` (or
`thread/start`) with `cwd`, `approvalPolicy: "never"`,
`sandbox: "danger-full-access"`, `model` and `developerInstructions` →
`turn/start` with the prompt and `effort` → streamed notifications until
`turn/completed`. Cancel sends `turn/interrupt`, and the thread id — reported
early — is persisted even on interruption, so an interrupted turn stays
resumable. The same protocol answers `model/list`, which is how Coffer reads
Codex's model catalogue ([Model Catalogue Read From the
Agent](model-catalogue-read-from-the-agent.md)).

Pros: both are the vendors' supported programmatic interfaces, with typed
messages and a real interrupt instead of a signal to a process. Everything the
platform needs is an option or a request field, not a command-line flag and a
stdout format parsed by hand. The adapters are symmetric — a pump task feeding
one queue that the stream drains — and each is the only module that knows its
agent's protocol, so upstream drift breaks one adapter.

Cons: two protocols to track, each still young (the SDK is pinned below 0.3;
app-server notifications have changed between Codex releases). The SDK's
bundled CLI can differ from the `claude` the user runs on PATH. A process is
spawned per turn on both sides, which costs start-up time per turn (resume
keeps the context). The agents' streaming schemas remain a moving target that
the mapping modules (`claude_sdk_mapping.py`, `codex_mapping.py`) absorb.

Wins because it is the lowest layer that still runs the user's real agent
while giving Coffer structured events, a clean interrupt and resumable
sessions.

### Option B — Shell out to each CLI's print mode per turn (`claude -p --output-format stream-json`, `codex exec --json`)

How it works — the design first shipped: each turn runs the CLI
non-interactively with `--resume <id>` (or `codex exec resume <id>`), reads
line-delimited JSON from stdout and maps it to events.

Pros: no library dependency; the exact binary the user runs; easy to
reproduce by hand.

Cons: stopping a turn means killing the process, with nothing telling the CLI
to leave its session in a resumable state; every per-turn parameter is an argv
flag whose presence depends on the installed CLI version; the stdout schema is
parsed without types; inline images and a bidirectional channel (Coffer
answering the agent mid-turn) are not available from `codex exec`. The
SDK and app-server adapters were adopted in 2026-06 (PRs #77, #82) because the
then-planned per-tool approval relay needed that bidirectional channel. When
the approval system was removed (PR #101), the SDK and app-server stayed for
the interrupt, typed events and parameter surface, and the print-mode adapters
(about 1,080 lines with their tests) were deleted as dead code (PR #146).

Loses on interrupt, parameter surface and schema robustness.

### Option C — Drive the interactive TUI through a pseudo-terminal

How it works: run `claude` or `codex` in a PTY, type the prompt, scrape the
screen.

Pros: identical to what a human sees, including features with no headless
equivalent.

Cons: output is ANSI screen state, not events; every UI change breaks the
scraper; no reliable way to know a turn ended or to read tool calls.

Loses on fragility.

### Option D — The TypeScript Agent SDK in a Node sidecar

How it works: a small Node process hosts the TypeScript Claude Agent SDK (the
first-party SDK with the widest surface) and talks to the daemon over a local
socket.

Pros: earliest access to new SDK features.

Cons: a second runtime to bundle and supervise inside a PyInstaller-built
daemon, a second IPC protocol to maintain, and a sidecar lifecycle to add to
detect-or-spawn — for parity the Python SDK already provides for what Coffer
uses.

Loses on distribution and process cost.

### Option E — Call the model API directly with Coffer's own tool loop

How it works: Coffer sends messages to the provider API and implements tool
execution itself.

Pros: full control of the loop, no subprocess, any provider.

Cons: it is not the user's agent: none of Claude Code's or Codex's tools,
skills, MCP configuration, project instructions, subscription login or session
history. Coffer would become a coding agent of its own, which it has decided
not to be.

Loses on the premise: Coffer manages agents, it does not replace them.

## Decision

Claude Code turns run through the Python Claude Agent SDK's `ClaudeSDKClient`,
and Codex turns through a `codex app-server` process spoken to over JSON-RPC on
stdio. Each turn opens a session with the conversation's stored session id,
model, effort, working directory, environment and appended context, streams
typed events into the platform's `AgentEvent`s, interrupts through the
protocol's own call, and persists the upstream session id for the next turn.
Both run with full permissions and no interactive prompt.

Rules a future change must respect:

- Each agent's protocol is known only to its adapter and mapping modules;
  the rest of the platform sees `AgentEvent`s.
- A new per-turn parameter goes through the SDK option or RPC field, never a
  side channel into the agent's config files.
- Every stream ends with exactly one terminal event, synthesised as an error
  if the agent process disappears mid-turn.

## Consequences

- Adding an agent means a provider and adapter pair speaking that agent's own
  programmatic interface, registered in `surfaces/http/chat_provider_wiring.py`.
- A Claude Code CLI too old for a requested option fails at connect rather than
  degrading silently; the SDK's bundled binary makes that rare.
- Upgrading `claude-agent-sdk` or Codex is a mapping-module change, tested
  against scripted fakes (`ClaudeSdkSession`, `CodexAppServerSession` seams)
  plus integration tests that skip when the binary is absent.
- Enforced by: the import-linter contract confining `claude_agent_sdk` to
  `infrastructure/chat`; `claude_sdk_agent.py`, `codex_agent.py`,
  `codex_app_server.py`, `codex_jsonrpc.py`.
