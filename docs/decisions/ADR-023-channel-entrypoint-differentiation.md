# ADR-023: Channel Entrypoint Differentiation Layer

> 中文版: [ADR-023-channel-entrypoint-differentiation.zh.md](./ADR-023-channel-entrypoint-differentiation.zh.md)

**Status**: Accepted
**Spec**: [009-channels](../../specs/009-channels/spec.md)

> **Amended (2026-06-20, simplification 8.4).** The per-binding workspace
> allowlist, the `/cwd` switch, and the peer `preferred_workspace` are
> withdrawn: channels run in the single Coffer-managed default workspace
> (`~/.coffer/workspace`). The `/agent` + `/model` switches and the
> entrypoint-differentiation core stand.

## Context

Spec 009 made Coffer the channel-entrypoint manager: an owner pairs an IM
account to a `channel:<name>` resource and drives any registered agent
(`builtin`, `claude_code`, `codex`) through the chat platform's seams.

What the entrypoint manager still lacked is the layer that makes it a
_switchboard_ rather than a single fixed wire: an owner could only talk to the
one agent baked into the channel config, in the one (operator-baked) working
directory, with no record of who drove what, and — on a platform that cannot
edit messages (SeaTalk) — no signal at all while a long bridged turn ran. These
are exactly the differentiators an entrypoint manager owns and that off-the-shelf
IM bots skip.

Two facts from the code shaped the design:

- A conversation **pins its `agent_key` for life** and the bridged providers
  fix **`cwd` at `init_conversation`**; there is no re-key path. But **`model`**
  for a bridged turn is read fresh from `agent_config` every time the adapter is
  rebuilt (once per turn).
- The bridged agents **require a `cwd`** (no default; a missing one is
  rejected) and that `cwd` had **no allowlist** — any host directory was
  accepted. Channels never offered the owner a way to choose it.

## Decision

1. **Structural vs parametric selection — one mental model for all switches.**
   - _Structural_ dimensions (`agent_key`, `cwd`) are pinned when a conversation
     is created and cannot change mid-conversation. Switching one **opens a new
     conversation**, carrying over the other dimension's sticky value; the old
     conversation stays in history. `/agent` is structural.
   - _Parametric_ dimensions (`model`) are re-read each turn. Switching one
     **takes effect on the next turn in the same conversation**. `/model` is
     parametric.

   This mirrors the providers' real contract (cwd/agent fixed at
   `init_conversation`; model read at `build_adapter`), so the command semantics
   are honest rather than papered over with a synthetic re-key.

2. **Per-channel agent routing is sticky, stored on the peer.** `/agent <key>`
   validates against the agent registry and records the choice as the peer's
   sticky preference; `/new` and lazy creation use the sticky agent, falling
   back to the channel's configured `default_agent`. The auxiliary
   (vault-facing) agent is not a routing target — routing is between the
   chat-path agents the registry exposes (`builtin`, `claude_code`, `codex`, and
   any future registered agent), with no channel-side code per agent (spec 009
   SC-004 preserved).

3. ~~**Workspaces are a channel-level allowlist and the cwd security boundary.**
   A channel declares a list of **named workspaces** (`{name, path}`), validated
   to exist at registration; an optional `default_workspace` names the one used
   when none is chosen. `/cwd <name>` selects among them (structural → new
   conversation). **A channel never accepts a bare filesystem path from an IM
   message** — an owner can only pick a name the operator pre-authorized.~~ —
   **Withdrawn (2026-06-20, simplification 8.4).** Channels now run in the
   single Coffer-managed default workspace (`~/.coffer/workspace`); there is no
   per-channel allowlist and no `/cwd` command.

4. **Model selection is a parametric passthrough, registry-backed only where a
   registry exists.** For `builtin`, `/model <name>` resolves against Coffer's
   model registry and sets the conversation's `model_id` override. For the
   bridged agents, `/model <name>` writes `agent_config["model"]` — the raw model
   string the upstream CLI understands — passed through unvalidated, because
   Coffer does not own that namespace; a typo surfaces as a CLI error relayed
   back to the chat. (This also fixes the Claude Code provider, which previously
   accepted a `model` option but never persisted one, so the CLI always chose.)

5. **Channel-driven work is first-class in the audit log.** A new event type
   records what the generic per-turn audit could not: `CHANNEL_TURN_STARTED` when
   an inbound message drives a turn (who/when/which channel/which agent/which
   conversation). Audit lives in the
   channel layer because that is the only place the channel + peer context
   exists; the existing free-form `details_json` carries the structured context
   with no schema change.

6. **Owner gate verifies sender identity, not just chat identity.** The inbound
   envelope carries a `sender_id` (Telegram `from.id`, SeaTalk `employee_code`);
   pairing records it on the peer, and the owner gate checks `chat_id` **and**,
   when the peer has a stored `sender_id`, the sender. This closes the
   group-chat hole (any member of a paired group chat previously passed a
   chat-id-only gate) while staying backward compatible: a peer paired before
   this change has a null `sender_id` and degrades to the chat-id-only gate.

7. **Turn completion is signalled explicitly, capability-agnostic.** After every
   turn the channel sends one compact fact summary as a fresh message — success
   (`done`, tool count, duration, tokens), error, or interrupted. It is a fresh
   `send_text`, not an edit, so it works identically on every platform; on
   SeaTalk (which cannot edit and showed nothing during a long bridged turn) it
   is the only end-of-turn signal the owner gets.

## Alternatives considered

- **Re-key a conversation's agent/cwd in place** instead of opening a new
  conversation — rejected; the providers fix both at `init_conversation` and a
  bridged CLI session is tied to its cwd, so an in-place re-key would be a
  fiction that breaks resume continuity.
- **Accept a bare cwd path from an IM message** (`/cwd /some/path`) — rejected;
  a remote-reachable entrypoint pointing an agent at an arbitrary host directory
  is the exact boundary the allowlist exists to hold.
- **Validate bridged model strings against a curated list** — rejected as
  cargo-cult; Coffer does not own the upstream CLI's model namespace and would
  have to chase it. Passthrough with a relayed CLI error is honest and cheap.
- **Stream token-level text and refresh a heartbeat during the turn** —
  rejected for now; a single completion summary is the high-value, low-noise
  signal, and block-level tool progress already exists where the platform can
  edit.

## Consequences

- The peer gains a column for the paired sender's identity (`sender_id`) and a
  sticky agent preference (`preferred_agent`); one migration covers them.
  No new table. (`preferred_workspace` and `workspaces`/`default_workspace`
  on config are withdrawn — see amendment above.)
- The command set grows by `/agent` and `/model`; both ride the existing
  slash-command seam in the channel core and select behavior from capabilities,
  so no adapter learns about them — the differentiation layer is
  channel-agnostic and any future channel inherits it (spec 009 SC-003
  preserved). (`/cwd` is withdrawn — see amendment above.)
- The audit log answers "who drove which agent through which channel" without a
  schema change.
