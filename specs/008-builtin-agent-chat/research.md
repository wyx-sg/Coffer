# Research — 008 Built-in Agent & Chat

Background and alternatives behind the built-in agent and chat surface. The
load-bearing engine decision is recorded as
[ADR-013](../../docs/decisions/ADR-013-langgraph-builtin-agent-engine.md).

## Why give Coffer its own agent at all

Until spec 008, Coffer only _managed_ external agents — it stored their config
and installed its MCP gateway into them, but never ran an LLM itself. A built-in
agent lets Coffer dogfood its own vault: it can call every MCP server / skill /
knowledge base / memory tool the gateway exposes, with no external CLI required.
It also gives non-developer users a chat surface that works out of the box once
a provider key is set. The external-agent runtime keeps the existing managed
agents usable from the same chat surface, so the user has one place to talk to
either.

## Why LangGraph for the built-in runtime

We needed an agent loop that (a) works with any mainstream provider, (b) supports
streaming token output and tool calls, (c) can consume MCP tools, and (d) gives
us a place to intercept tool execution for human-in-the-loop confirmation.

**LangGraph** (chosen):

- `init_chat_model` resolves a provider-qualified model string
  (`anthropic:…`, `openai:…`, `ollama:…`, …) so the `model` config field is the
  only switch needed to change providers — no per-provider code in Coffer.
- `create_react_agent` gives a ready tool-calling loop; `astream_events` exposes
  token deltas, tool starts, and tool ends as a uniform event stream we map onto
  the `AgentRuntime` port.
- `langchain-mcp-adapters` (`MultiServerMCPClient`) turns Coffer's own `/mcp`
  gateway into LangChain tools, so the agent gets the whole vault toolset by
  connecting to `127.0.0.1` with the daemon token.
- Tool execution stays under Coffer's control (the agent calls a Python callable
  we own), which is exactly the seam we need to gate confirm-listed tools.

The cost is a heavy dependency tree. We absorb it by confining LangChain /
LangGraph to `infrastructure/chat/builtin_runtime.py` and importing it lazily
inside `stream`, so the rest of the codebase — and startup wiring — never needs
the engine importable. importlinter Contract 7 enforces the boundary.

### Alternatives considered

**Raw provider SDKs (Anthropic / OpenAI / Ollama clients) directly.** Rejected.

- We would re-implement a tool-calling loop, streaming normalization, and
  per-provider message shaping ourselves, then maintain N provider integrations.
- MCP-tool plumbing would be hand-rolled per provider.
- The only upside (no LangChain dependency) is neutralized by confining the
  engine to one module behind a port.

**LlamaIndex agents.** Rejected.

- Strong on retrieval/index workflows, but its agent + streaming + MCP-tool story
  is a weaker fit for a general tool-calling chat loop than LangGraph's, and we
  do not need its indexing core (Coffer's knowledge bases are their own kind).
- Would still need the same port + isolation discipline, with less leverage.

## Provider-agnostic model resolution

The `model` config field is a single provider-qualified string, e.g.
`anthropic:claude-sonnet-4-6`. The runtime splits on the first `:` to get the
provider, then hands the whole string to `init_chat_model`. Credentials:

- Cloud providers (`anthropic`, `openai`) require a key. The runtime resolves it
  from the keychain via `credential_ref`, falling back to the provider's
  conventional environment variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). If
  neither is present it raises `LlmNotConfigured` **before** any message is
  persisted, so the API returns `503 LLM_NOT_CONFIGURED` cleanly.
- Local providers (`ollama`) need no key; the absence of a key is not an error.

Optional `temperature` / `max_tokens` are passed through only when set, so the
provider's own defaults apply otherwise.

## External-agent headless invocation

Coffer drives managed external agents by spawning their CLI as a local
subprocess in headless streaming mode and mapping stdout to runtime events. Per
agent type:

- `claude_code` → `claude -p <prompt> --output-format stream-json --verbose`;
  the runtime reads `stream-json` assistant blocks and emits their text.
- `codex` → `codex exec --json <prompt>`.

The binary is resolved from an explicit override
(`COFFER_CHAT_BIN_<TYPE>`) or `PATH`; a missing binary surfaces as a structured
`UPSTREAM_UNAVAILABLE` error (the assistant message is marked `failed`) rather
than crashing. Each agent runs under its registered `config_dir` (passed via
`CLAUDE_CONFIG_DIR` / `CODEX_HOME`), so it sees the same MCP gateway Coffer
already installed into it. The child is always reaped — on normal end, error,
stop, and daemon shutdown — so no orphan processes remain (SC-003).

The line mapper is deliberately tolerant: it handles a `{"text": …}` shape (our
stubs), Claude Code `stream-json` assistant blocks, and a plain-text fallback,
and ignores unknown control JSON. `cursor` and other types without a documented
headless streaming mode are out of scope as chat targets in this spec.

## Confirmation approaches

The goal: a tool the user marked sensitive must not run without explicit
approval (SC-005), and an unanswered confirmation must not corrupt the store.

- **Built-in runtime (Coffer controls execution).** Each gateway tool whose name
  matches the agent's `confirm_tools` globs is wrapped. When the agent calls it,
  the wrapper emits a `ConfirmationRequest` event (tool name + arguments) and
  awaits a decision future instead of running. `ChatService.resolve_confirmation`
  resolves that future: approve runs the original tool and returns its result;
  deny returns a "declined" string to the agent so it continues gracefully. Stop
  resolves all pending futures as denied. This is the strong guarantee path.
- **External-agent runtime.** Coffer does not control the agent's tool execution,
  so confirmation is enforced only where the agent CLI exposes a permission-prompt
  hook; otherwise the agent runs under its own configured permission policy
  (surfaced to the user). In v1 `resolve_confirmation` is a no-op for external
  runtimes and `confirm_tools` is empty for them. Wiring a CLI permission hook is
  deferred.

### Confirmation alternatives considered

**Pre-flight approval of the whole turn (approve once, then run freely).**
Rejected — too coarse; a turn may reach a sensitive tool only after several safe
ones, and the user wants per-tool control.

**Policy-only blocking (deny sensitive tools outright, no prompt).** Rejected —
removes the human-in-the-loop value; the user explicitly wanted approve/deny.

## Persistence shape

Conversations and messages are control-plane data, so they live in SQLite (not
files). Messages use an autoincrement `seq` primary key for stable in-conversation
ordering plus a unique `mid` for the domain id; tool calls are stored as a JSON
summary array embedded in the message (name + truncated arg/result summaries
only — never full payloads — matching the gateway invocation-logging discipline).
Streaming deltas are transient: only the finalized assistant content and
tool-call metadata are persisted, so a restart returns history without re-running
any turn.

## Auto-title

After the first user/assistant exchange on a placeholder-titled conversation, a
short title is generated. A `TitleGenerator` port may produce one from the
exchange; if it is absent or fails, the title falls back to a truncated first
user message (first line, capped). Title generation never blocks or fails the
turn — it runs in the finalize path with errors suppressed.
