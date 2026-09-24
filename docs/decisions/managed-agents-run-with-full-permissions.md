# Managed Agents Run With Full Permissions; Owner Pairing Is the Gate

**Status**: Accepted
**Date**: 2026-06-18
**Deciders**: Yuxing Wu
**Related**: [Channel Owner Gate](channel-owner-gate.md), [Driving Agents Through the SDK and App Server](driving-agents-through-sdk-and-app-server.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), [SeaTalk WebSocket Inbound](seatalk-websocket-inbound.md), [Telegram Long Polling](telegram-long-polling.md), spec channels "Pair exactly one owner with a single-use code", spec channels "Gate inbound traffic on sender identity", spec chat "Interrupt the watched turn from the page", [principles](../../docs-site/architecture/principles.md) ("Not a firewall or security boundary"), research note [IM agent bridges](../research/im-agent-bridges.md), PR #77, PR #82, PR #101, PR #398, PR #410, PR #431

## Context

Coffer drives the user's own coding agents — Claude Code through
`claude-agent-sdk`, Codex through `codex app-server` — from two places: the web
Chat page and IM channels (SeaTalk, Telegram). A channel turn usually runs while
the owner is away from the machine, typing on a phone.

Both agents can ask a human before running a tool. Claude Code's SDK raises
`can_use_tool`; Codex's app-server sends a `requestApproval` JSON-RPC request.
Coffer once relayed both: the turn parked on an `ApprovalGate`, and the owner
allowed or denied the call from a web `ApprovalCard` or from an IM button card
(PR #77 for Claude Code, PR #82 for Codex).

That relay never worked end to end with a real agent. The SDK's `can_use_tool`
path failed at runtime with `Stream closed`, because the control stream was not
established in Coffer's run mode. Only allowlisted, auto-approved tools ran.
The interactive path passed its tests only against fakes. It also cost real
surface: an approval domain and channel, an `ApprovalRequest` event, two agent
relays, approval cards and callback handling on each IM adapter, a web card, a
`/conversations/{id}/approvals` route and an audit event.

The trust question underneath is: who can make an agent act at all? A channel
obeys exactly one paired owner (spec channels "Pair exactly one owner with a
single-use code"). A message from anyone else is dropped before a turn starts,
and in a group the sender gate fails closed ([Channel Owner Gate](channel-owner-gate.md)).
Both IM transports are outbound-only — SeaTalk over a websocket the daemon
opens, Telegram by long polling — so no public callback URL exists for a third
party to post to (PR #431 removed SeaTalk's webhook). The web page is behind the
daemon's token and loopback bind. So every instruction an agent acts on was
issued by the owner.

## Options Considered

### Option A — Full permissions; owner pairing is the only gate (chosen)

Claude Code runs with `permission_mode="bypassPermissions"`
(`infrastructure/chat/claude_sdk_agent.py`). Codex threads start with
`approvalPolicy: "never"` and `sandbox: "danger-full-access"`
(`infrastructure/chat/codex_agent.py`). There is no approval relay, no approval
UI and no permission setting. The owner's control over a running turn is to
watch it and stop it: the web page can interrupt the turn it is watching and
continue the conversation ([Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md)),
and a channel has its own stop control.

Pros: turns run unattended, which is the point of driving an agent from a
phone; the agent behaves as it does when the user runs the CLI in their own
terminal, where most users already run it permissively; no half-working
affordance suggests protection that is not there; all trust rests on one gate
that can be reasoned about. Cons: a prompt-injected instruction inside content
the agent reads (a web page, an issue, a file) runs with the owner's full
filesystem and network access; a Codex turn is not sandboxed at all; a
compromised IM account is a compromised machine. It wins because a per-tool
prompt only re-confirms instructions the owner already gave, and the prompt
path had never worked. Per the principles, Coffer is not a security boundary;
the agent's own permission system is the user's to configure when they run it
directly.

### Option B — Per-tool approval relayed to the web and IM (built in PR #77/#82, removed in PR #101)

Every tool call the agent wants approval for is forwarded as a card; the turn
waits for the owner's tap.

Pros: a human sees each side-effecting call before it happens; catches injected
instructions. Cons: an approval per call makes an unattended phone-driven turn
unusable — the owner either taps "allow" reflexively or stops using the channel;
it duplicates the gate pairing already provides; and the transport never worked
(`Stream closed`). Reviving it meant fixing the SDK control stream, keeping two
relay protocols and four card renderers in step, and building a timeout policy
for unanswered cards. It lost on cost against a benefit the owner did not want
in practice.

### Option C — Per-channel trust levels

Each channel carries a level — read-only, ask-for-writes, full — mapped onto
the agents' permission modes.

Pros: a shared or less-trusted channel could be restricted without affecting
the owner's private one. Cons: "ask-for-writes" needs the approval relay of
Option B; "read-only" needs a per-agent mapping of what counts as a write
(Claude Code has plan mode; Codex has `read-only` sandbox), which differs by
agent and changes with releases. Every channel today has exactly one owner, so
there is no less-trusted audience to restrict. It loses as a setting with no
user; it is the natural shape if multi-member channels ever arrive.

### Option D — Codex in `workspace-write` sandbox

Keep approvals off but confine Codex writes to the working directory.

Pros: limits blast radius for Codex; Codex's sandbox is a real OS-level
mechanism. Cons: the sandbox also blocks network access and writes outside the
workspace that ordinary tasks need (package installs, git credentials, a sibling
repo), so turns fail in ways the owner can only diagnose at the machine; Claude
Code has no equivalent, so the two agents would behave differently for the same
request. It loses on the failure mode: a remote turn that silently cannot do its
job is worse than one that can.

### Option E — Read-only by default for IM-driven turns

Web turns get full permissions; channel turns run read-only unless the owner
escalates.

Pros: the remote, less-observed surface is the restricted one. Cons: the main
reason to drive an agent from IM is to get work done away from the desk, which
is mostly writes; escalation needs either the approval relay or a per-message
syntax the agent would also have to honour. It loses on the primary use case.

### Option F — Gateway-level approval of write-class tools

Hold a write-class MCP tool call at Coffer's gateway until approved, independent
of the agent's own permission system.

Pros: agent-agnostic, because it sits on Coffer's own call path; the gateway
already knows the caller and the tool. Cons: it sees only MCP tools routed
through Coffer, not the agent's built-in shell and file tools, which carry most
of the risk; each tool must be classified as write or read. It was built for
unattended workflow runs (PR #398, with a `ToolCallGatePort` applied only when a
run identity is on the session), and parked with the workflow kind on the
`feature/workflow` branch (PR #410). Ordinary conversations never passed through
it. It remains the candidate if unattended runs return, because there nobody is
driving the turn.

## Decision

Managed agents run with full permissions on every surface: Claude Code with
`bypassPermissions`, Codex with `approvalPolicy: "never"` and
`sandbox: "danger-full-access"`. Coffer gates who may start and steer a turn,
not which tools a turn may call. That gate is owner pairing on channels, with
outbound-only IM transports and a fail-closed sender check, plus the daemon's
token on the web. There is no approval relay, approval UI, approval route or
approval audit event.

A future change must keep these properties:

- Channel inbound stays outbound-only or authenticated. A public, unauthenticated
  inbound path would turn "only the owner can issue instructions" into an
  assumption.
- Anything that re-introduces per-call gating is a new decision. It must not
  come back as dormant machinery or a UI affordance that cannot actually gate.

## Consequences

- The turn seam (`run_turn(*, history, attachments)` in
  `application/chat/ports.py`) has no approval channel, and the agent event
  union and channel capabilities carry no approval types.
- A channel-driven agent can run any command the user could, anywhere the user
  could. The owner's defences are pairing, watching, and interrupting.
  Prompt injection through content the agent reads is not mitigated by Coffer.
- The owner-gate code is security-critical. Pairing, the sender gate and group
  addressing rules are specified in spec channels and covered by
  [Channel Owner Gate](channel-owner-gate.md).
- Gating can be re-added for a real multi-trust scenario — a shared channel, or
  unattended runs — through Option C or Option F, behind a setting that
  defaults to today's behaviour.
