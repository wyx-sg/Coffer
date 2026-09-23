# A Workflow Run's Writes Are Gated at the Gateway

**Status**: Accepted
**Date**: 2026-09-17
**Deciders**: Yuxing Wu
**Spec**: [workflow](../../openspec/specs/workflow/spec.md)
**Amends**: [Remove the Tool-Approval System](./remove-tool-approval.md) — its removal stands for every conversation a person is driving; this adds a gate for the one case it named as re-introducible, and puts it somewhere else entirely

## Context

Coffer does not gate individual tool calls. That was decided deliberately and
the reasoning holds: a channel obeys one paired owner, every instruction the
agent acts on is one the owner just issued, and a per-tool prompt re-confirms
what the owner already authorised. Friction, not safety. The agents run with
`permission_mode = bypassPermissions` and Codex with `approvalPolicy = "never"`.

A workflow run breaks the premise that argument rests on. Its tool calls are not
the owner's live instructions. They are inferences a node's agent drew from a
template the owner wrote days ago, executed while the owner is asleep. Between
"the owner just asked for this" and "a template said this stage files a ticket"
there is a real gap, and the run crosses it unattended, with reach into Jira,
Confluence, GitLab and a deploy platform.

The previous approval system also failed for a second reason, separate from
redundancy: **it was built at the agent's permission layer and never worked
end-to-end.** The claude SDK's `can_use_tool` relay died with `Stream closed`
because the control stream is not established in Coffer's run mode. Interactive
approval was exercised only against fakes. Any gate that goes back to that layer
inherits that failure.

## Decision

A workflow run's **upstream tool calls are gated at Coffer's MCP gateway**, and
only a workflow run's. Three parts:

**Where the gate lives.** `MCPGatewaySession._handle_tools_call` is the single
point every tool call passes through — built-in tools and upstream tools alike.
The gateway is Coffer's own server, so holding a call means not yet returning its
JSON-RPC response. No agent-side control stream is involved, which is precisely
why this can work where `can_use_tool` could not.

**How a call is attributed to a run.** The shim already stamps its launch cwd and
agent identity into the `initialize` handshake's `_meta` bag. A node's turn adds
one more key by the same route: Coffer sets the run identity in the agent
process's environment (`ClaudeAgentOptions.env`, which the Codex side already
uses), the CLI passes it to the shim it spawns, and the shim reports it. A
session with no run identity is an ordinary conversation and is not gated.

**What is gated.** Upstream tools judged write-class. A tool with no recorded
judgement is treated as write-class and the developer is asked once; the answer
is remembered. Built-in `coffer__*` tools are not gated — they reach the vault,
which is the developer's own machine.

The removal ADR stands everywhere else. A channel conversation, a chat, an agent
the owner is driving: no gate, unchanged.

### Where the gate touches code outside the workflow layer

Three seams, each small, so a review can find every one of them:

1. **The shim reports a run identity.** `surfaces/shim/bootstrap.py` reads
   `COFFER_RUN_CONTEXT` (`"<run_id>/<node_attempt_id>"`) from its environment
   and stamps it into the `initialize` handshake's `_meta` as `coffer/run`. The
   key is omitted on every ordinary launch, so a session without it looks
   exactly like one from before the key existed.
2. **A node's turn sets that variable.** Both chat providers
   (`infrastructure/chat/claude_sdk_provider.py`, `codex_provider.py`) take a
   `ConversationEnv` lookup and overlay what it returns on the agent process's
   environment. The composition root wires it to the workflow's
   `conversation_env_lookup`, which answers only for a conversation that is a
   node attempt, and answers nothing for any other conversation.
3. **The gateway consults a port, not the workflow.** The import fence forbids
   `application.mcp` from importing `application.workflow`, so the hold is a
   `ToolCallGatePort` Protocol in `application/mcp/gateway_gate.py`.
   `MCPGatewaySession` dispatches every upstream call through
   `gated_upstream_call`, which awaits the port only when a gate is wired and
   the session carries a run identity. The composition root fills a late-bound
   holder with `application/workflow/gate.py`'s `WorkflowToolGate`. Built-in
   tools are dispatched before that point and never reach it.

The gate's memory is data rather than code: an `mcp_server`'s config carries a
`tool_write_class` map, read and written through `application/mcp/tool_class.py`.

## Consequences

**The gate is not a sandbox, and must not be described as one.** It covers what
Coffer brokers. A node's agent has a shell in the run's working directory: it can
`git push`, `curl`, or run a deploy CLI directly, and none of that passes through
the gateway. What the gate buys is that the *brokered* paths — the registered MCP
servers holding the credentials Coffer keeps — cannot be used unattended without
a decision. Templates should route external writes through those paths for the
gate to be worth anything, and the run's isolated working directory is what
limits the rest.

**Unknown-means-write costs friction on day one.** The first run against a new
upstream server will stop on tools that only read. That is the intended
direction of the error: a false stop is a question, a false pass is a write to a
live system at 3am.

**A held call is a held turn.** The agent sees a slow tool call. A call held past
its approval's expiry fails with an explicit reason rather than hanging, and the
node moves to `waiting_review` — the agent is never left with a silently dropped
call, which is the failure mode that makes an agent retry or invent.

**One more thing can refuse a tool call.** The gateway's refusal path grows a
reason that is not "upstream is down". Diagnosis has to keep them distinct.

## Alternatives considered

- **Gate at the agent's permission layer again** (`can_use_tool`, Codex
  `requestApproval`). Rejected: this is the exact mechanism that was removed for
  not working, and the reason it did not work — no control stream in Coffer's run
  mode — has not changed.
- **No gate; trust the template.** Rejected: the template is written once and the
  run executes forever after. A template that says "deploy" is not a decision
  about *this* deploy.
- **Gate every conversation, not just runs.** Rejected: that re-litigates the
  removal ADR and reintroduces exactly the friction it correctly removed. A
  person watching their own agent work does not need to approve it twice.
- **Let the node execute writes itself, with the agent forbidden to.** Rejected:
  it moves every integration into Coffer's own code — the thing skills exist to
  avoid — and an agent that is merely *asked* not to write is not prevented from
  writing.
