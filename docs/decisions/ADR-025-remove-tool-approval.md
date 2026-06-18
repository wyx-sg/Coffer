# ADR-025 — Remove the Tool-Approval System; Owner-Pairing Is the Gate

> 中文版: [ADR-025-remove-tool-approval.zh.md](./ADR-025-remove-tool-approval.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** Yuxing Wu
- **Spec:** [008-agent-chat](../../specs/008-agent-chat/spec.md) and [009-channels](../../specs/009-channels/spec.md) (removal — no new spec number; both `spec.md` files are updated alongside this ADR)
- **Supersedes:** the **"approval seat"** job of [ADR-021](./ADR-021-chat-as-vault-console.md); removes the per-tool approval relay introduced in Spec 008 and bridged to IM in Spec 009 ([ADR-014](./ADR-014-channel-adapter-framework.md), [ADR-023](./ADR-023-channel-entrypoint-differentiation.md))

## Context

Spec 008 gave the chat platform a per-tool **human-approval** capability: an
agent that wanted to run a tool emitted an `ApprovalRequest`, the turn parked on
an `ApprovalGate`, and a human allowed/denied it — from the web `ApprovalCard`
(ADR-021's "approval seat") or, after Spec 009, from an IM interactive
button/card. The claude SDK relayed it through `can_use_tool`; Codex through its
`requestApproval` JSON-RPC.

Two things make this the wrong shape now:

1. **It is redundant with owner-pairing.** A channel obeys exactly one paired
   owner; non-owner messages are ignored, and the web console is the owner too.
   Every instruction the agent acts on is one the owner just issued. A per-tool
   prompt re-confirms what the owner already authorized — friction, not safety.
   This is why peer agents (Claude Code, Codex, OpenClaw, Hermes) driven from a
   chat surface do not gate individual tool calls: the human is already in the
   loop by issuing the request.

2. **The relay never worked end-to-end with a real agent.** The claude SDK
   `can_use_tool` path failed at runtime with `Stream closed` (the control
   stream was not established in Coffer's run mode); only allowlisted, auto-
   approved tools ran. The interactive approval was tested with fakes but was
   effectively dead in production — "looks present, can't be used."

Keeping a broken, redundant capability costs real surface: an `ApprovalGate`
domain + channel, an `ApprovalRequest` event, `can_use_tool`/`requestApproval`
relays, SeaTalk/Telegram approval cards + callback handling, a web `ApprovalCard`
and approval seat, an HTTP `/approvals` route, a `CHANNEL_APPROVAL_RESOLVED`
audit event, and their tests and docs.

## Decision

**Remove the entire interactive tool-approval system.** Agents always run with
full permissions:

- claude SDK / claude CLI → `permission_mode = bypassPermissions`.
- Codex app-server → `approvalPolicy = "never"`, `sandbox = "danger-full-access"`.

There is no `permission_mode` configuration surface, no approval relay, no
approval UI on web or IM, and no approval audit event. The web console keeps its
**observe** role over channel-driven conversations; it no longer takes an
approval seat. Owner-pairing (pairing code + signature verification on the
public callback) is the trust boundary.

Deleted: `ApprovalGate`/`ApprovalChannel`/`ApprovalRequest`/`ApprovalDecision`/
`ApprovalClick`/`ApprovalNotFound`, `submit_approval`, `can_use_tool`, the Codex
approval handlers, channel `send_approval_prompt`/`resolve_approval_prompt`/
`on_approval_click` and `supports_buttons`, the web `ApprovalCard`, the
`/conversations/{id}/approvals` route + `ApprovalSubmit` schema, and the
`CHANNEL_APPROVAL_RESOLVED` audit event. Spec 008 User Stories 6/11, Spec 009
User Story 5, and their FR/SC/scenarios are removed.

## Consequences

- **Simpler platform, honest surface.** The turn seam is `run_turn(*, history)`
  with no approval channel; the `AgentEvent` union and channel capabilities
  shrink. No dead "approval" affordance that cannot actually gate anything.
- **Security rests on one gate.** With no per-tool prompt, all safety is in
  owner-pairing and callback signature verification. The IM entrypoint is
  public-reachable, so those must stay correct — but they were always the real
  gate; the per-tool prompt added no protection against the owner themselves.
- **Full filesystem/exec access by default.** A channel/web agent can run any
  command in its working directory (and, for Codex, outside the sandbox). This
  matches how the user already runs these CLIs locally, and is the accepted
  trade for an unattended assistant the owner drives.
- **Re-introducible later.** If a future use case wants gating (e.g. a shared or
  less-trusted channel), the seam can be re-added behind a setting; it is not
  load-bearing for anything today, so removing it now is cheap to reverse.

## Alternatives considered

- **Keep the relay, fix `Stream closed`, add a permission-level setting** (a
  global read-only / read-write-with-approval / bypass toggle, approvals
  forwarded to the channel). Rejected: it invests in re-confirming the owner's
  own instructions and carries the cost of a broken transport to revive, for a
  capability owner-pairing already covers. YAGNI; re-add if a real multi-trust
  scenario appears.
- **Bypass by default, keep the machinery dormant.** Rejected: leaves dead code
  and a "looks present, can't be used" approval UI — the worst of both.
