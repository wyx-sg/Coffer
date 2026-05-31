# ADR-013: LangGraph as the Built-in Agent Engine, Behind the AgentRuntime Port

**Status**: Accepted
**Date**: 2026-06-01
**Deciders**: Yuxing Wu
**Related**: spec `008-builtin-agent-chat` (FR-004, FR-006, FR-008, SC-006), spec `001-mcp-gateway` (the MCP gateway the agent consumes), [ADR-007](ADR-007-everything-is-a-resource-kind.md)

## Context

Spec `008-builtin-agent-chat` gives Coffer its own agent — a real LLM loop that
must (a) work with any mainstream provider the user configures (Anthropic,
OpenAI, local Ollama, …), (b) stream token output and tool calls live, (c)
consume Coffer's own MCP gateway tools so the agent can use every MCP server /
skill / knowledge base / memory the vault manages, and (d) expose a point where
Coffer can intercept tool execution to pause for human-in-the-loop confirmation
of sensitive tools.

Coffer's constitution requires a layered architecture: domain and application
layers stay free of heavyweight third-party engines; such dependencies live only
in `infrastructure/` behind a port. Any agent engine we pick brings a large
dependency tree, so the engine must be confinable.

The same chat surface must also drive **external** managed agents (`claude_code`,
`codex`) as local headless subprocesses. So the chat/conversation layer needs a
single abstraction that both an internal LLM loop and an external subprocess can
satisfy — it must not be coupled to whatever engine powers the built-in agent.

## Decision

**The built-in agent's LLM loop is implemented with LangGraph, confined to
`coffer/infrastructure/chat/builtin_runtime.py`, and reached only through an
`AgentRuntime` port defined in the application layer.** A
`CompositeRuntimeFactory` selects between the LangGraph built-in runtime and the
subprocess external-agent runtime by the conversation target's kind; both
implement the same port, so `ChatService` is engine-agnostic.

Concretely:

- **Provider-agnostic model resolution.** The `builtin_agent` config carries a
  single provider-qualified `model` string (e.g. `anthropic:claude-sonnet-4-6`).
  The runtime hands it to LangChain's `init_chat_model`, so changing providers is
  a config edit with no Coffer code change. Credentials resolve from the keychain
  (`credential_ref`) with a fallback to the provider's conventional environment
  variable; a missing key raises `LlmNotConfigured` (→ 503) before anything is
  persisted.
- **Tool-calling loop.** `langgraph.prebuilt.create_react_agent` provides the
  loop; `astream_events` yields token deltas, tool starts, and tool ends, which
  the runtime maps onto the port's `RuntimeEvent` stream.
- **Gateway tools.** `langchain-mcp-adapters` (`MultiServerMCPClient`) connects
  to Coffer's own `/mcp` endpoint on `127.0.0.1` with the daemon token and turns
  the gateway into LangChain tools, gated by the `use_gateway` flag.
- **Confirmation seam.** Because Coffer owns the tool callables, a tool whose
  name matches `confirm_tools` is wrapped to emit a `ConfirmationRequest` and
  await an approve/deny decision before running — the human-in-the-loop guarantee
  (SC-005).
- **Isolation.** LangChain/LangGraph are imported **lazily inside `stream`**, so
  importing the runtime module or wiring the factory at startup never requires
  the engine to be installed. importlinter **Contract 7** (`forbidden`, source
  `coffer.domain` + `coffer.application`, forbidding `langgraph` / `langchain*`)
  enforces that the engine never leaks out of infrastructure, backing SC-006.

## Consequences

**Positive**

- One config field switches providers; no per-provider integration code.
- LangGraph's loop + `astream_events` + `langchain-mcp-adapters` give streaming,
  tool calls, and MCP-tool consumption for free, so Coffer writes only the
  mapping to its port.
- The `AgentRuntime` port keeps the chat layer identical for the built-in and
  external runtimes, and lets us add more runtimes later without touching
  `ChatService`.
- Engine churn is absorbed in one module; the rest of the codebase — and CI's
  layer checks — never sees LangChain.
- The confirmation seam is a natural consequence of Coffer owning tool execution
  in the built-in runtime.

**Negative**

- A heavy dependency tree (`langgraph`, `langchain`, `langchain-core`, the
  provider adapters, `langchain-mcp-adapters`) enters the backend. Mitigated by
  confinement + lazy import + the importlinter contract.
- LangChain's APIs are loosely typed; the built-in runtime needs a mypy override
  for that one module.
- LangChain/LangGraph API churn is real; we accept absorbing it in
  `infrastructure/chat/` only.
- Confirmation enforcement is strong only for the built-in runtime; external
  agents run under their own permission policy in v1 (a CLI permission hook is
  deferred).

## Alternatives Considered

**Raw provider SDKs (Anthropic / OpenAI / Ollama clients) directly.** Rejected.

- We would re-implement the tool-calling loop, streaming normalization, and
  per-provider message shaping, then maintain a growing set of provider
  integrations and hand-roll MCP-tool plumbing for each.
- The only benefit — no LangChain dependency — is already neutralized by
  confining the engine to one module behind the port.

**LlamaIndex agents.** Rejected.

- Its strength is retrieval/indexing workflows; Coffer's knowledge bases are
  their own kind and do not need LlamaIndex's index core.
- Its agent + streaming + MCP-tool story is a weaker fit for a general
  tool-calling chat loop than LangGraph's, while still requiring the same port +
  isolation discipline — less leverage for the same constraints.

**Couple the chat layer directly to the chosen engine (no port).** Rejected.

- It would make the external-agent subprocess runtime a second-class citizen and
  violate the layered-architecture constraint, leaking a heavyweight engine into
  application code and forbidding the importlinter contract that SC-006 requires.
