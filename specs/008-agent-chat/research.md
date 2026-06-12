# Research — 008 Agent Chat

Design decisions for the chat platform and the built-in agent. The first four
items are the platform-seam decisions of this revision; the rest record the
still-standing decisions of the built-in agent.

## 1. The agent-provider registry as the seam

**Question**: How does the chat surface reach an agent without depending on a
specific one?

**Decision**: A turn, a conversation's creation, and its teardown all go through
an `AgentProviderRegistry` keyed by the conversation's `agent_key`. The
orchestrator, persistence, and REST/SSE contract know only the registry and the
`AgentProvider` / `AgentAdapter` protocols. A second agent is one
`registry.register(provider, display_name)` call in the composition root — no
change to the chat page, the schema, or the wire contract (SC-007).

**Alternative rejected**: keeping the built-in agent wired straight into the
orchestrator and "adding a seam later". An untested seam is not a seam; the
platform is only real if a second provider can be added today, which the
approval-flow test's fake provider demonstrates.

## 2. A self-contained `AgentAdapter`

**Question**: What does a turn hand an agent?

**Decision**: `run_turn(*, history, approvals)` — nothing else. An agent's
model, tools, system prompt, and configuration are its own; its provider
injects them when it builds the adapter (`build_adapter`, once per turn). An
agent that brings its own model and tools (rather than Coffer's configured
model + gateway) plugs in unchanged. History trimming moves into the built-in
adapter, because the context budget is an agent-specific concern.

This also relocates `NoModelConfigured`: it is raised by
`BuiltinAgentProvider.build_adapter`, called inside `start_turn` before the user
message is persisted, so a no-model turn still fails as a pre-stream 409.

## 3. The human-approval channel

**Question**: How does a turn pause for a human decision?

**Decision**: An inbound channel. `ApprovalGate.wait(request_id)` awaits an
`asyncio.Future`; the concrete `ApprovalChannel` resolves that future when
`POST .../approvals` delivers a decision. The agent emits an `ApprovalRequest`
event (forwarded to the SSE stream as `approval_request`) and `await`s
`wait(...)`. Interrupting the turn cancels the task, which raises
`CancelledError` inside `wait()` — the contract's stated behaviour.

The channel is a **platform** capability, not a built-in-agent feature: the
built-in agent relies on the gateway's capability gating and never calls
`wait()`. The channel still ships complete and is proven end-to-end by an
integration test whose fake provider's adapter does request approval.

**Alternative rejected**: an outbound callback the orchestrator passes into the
agent. A pull-based `wait()` keeps the agent in control of when it blocks and
makes cancellation fall out of asyncio for free.

## 4. Interruption vs. deletion

**Question**: A turn task can be cancelled for two reasons — what distinguishes
them?

**Decision**: Both cancel the `asyncio.Task`. They differ in the handler:

- **Interrupt** (`interrupt_turn`, `POST .../interrupt`): the partial assistant
  message (text + tool blocks produced so far) is persisted `status='complete'`
  with `stop_reason='interrupted'`, and a terminal `TurnDone` is streamed. The
  conversation keeps the record and stays usable.
- **Delete** (`cancel_turn`, conversation deletion): nothing is persisted — the
  conversation row is being removed anyway.

The `_ActiveTurn` record carries an `interrupted` flag the task's
`CancelledError` handler reads to choose the path.

## 5. Agent configuration storage

**Question**: Where does an agent's per-conversation configuration live?

**Decision**: `agent_config` is opaque at the wire and registry level; each
provider interprets and stores it in `init_conversation`. The built-in agent's
only configuration is the model, and the `conversations.model_id` column
already holds it — so the built-in provider maps `agent_config["model_id"]`
onto that column and **no new column or migration is needed**. A future
provider that needs richer config brings its own table; the `init_conversation`
seam keeps that change local. `POST /conversations` therefore takes
`{agent_key, agent_config}` and no longer a top-level `model_id` (per-turn
model switching still uses `PATCH /conversations {model_id}`, a built-in-agent
convenience on the same column).

## 6. Agent framework, multi-provider, in-process gateway (unchanged)

The built-in agent's loop is LangGraph `create_react_agent`; LLM clients are
built through LangChain's provider packages (`anthropic`, `openai`, `ollama`);
credentials are keychain references resolved at runtime. The agent consumes
Coffer's MCP gateway in-process via one `MCPGatewaySession`
(`coffer-builtin-agent`). All LangGraph/LangChain imports stay confined to
`infrastructure/chat` (Contract 9). These decisions are carried forward
unchanged from the earlier 008 draft.

## 7. Conversation persistence & streaming (unchanged)

Conversations, messages, and models are Coffer-owned SQLite tables, not
Resources. LangGraph runs statelessly per turn; Coffer's tables are the system
of record. The turn runs as a detached `asyncio.Task` draining an
`asyncio.Queue` to an `EventSourceResponse`; a client disconnect cancels only
the drain. A startup sweep flips any `streaming` row to `failed`.

## 8. Out of scope

User-created/edited agents; a registry-management GUI; remote channels;
per-agent capability scoping beyond gateway gating + the approval channel;
conversation summarisation, search, export.
