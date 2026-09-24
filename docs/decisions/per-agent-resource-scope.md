# Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md),
[Kind Plugin Contract](kind-plugin-contract.md),
[Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md),
[Channel Owner Gate](channel-owner-gate.md),
[Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md),
[Cross-Platform Skill Delivery](cross-platform-skill-delivery.md),
[stdio Shim Bridge](stdio-shim-bridge.md),
spec resource-framework "Carry a per-agent reach on every resource",
spec mcp-gateway "Gate server exposure by scope per session",
spec mcp-gateway "Take the agent identity from the handshake",
PRs #296, #380, #404, #406

## Context

Some resources are only useful to one of the agents Coffer manages
(`claude_code` and `codex`): an MCP server whose tools only make sense to one
CLI, a skill written against Claude Code's frontmatter, a provider connection
whose wire protocol only one agent speaks, a chat channel that should drive one
agent and not the other. Without a way to say so, the gateway exposed every
server's tools to every agent and out-of-place servers failed or added noise.

Before this decision the question had been answered separately by several
kinds. Skills had a consumer-side "follow" flag plus per-agent exclusions and a
per-binding enable flag; providers had `compatible_agents` inside their config
(PR #226); MCP servers had nothing. Three kinds, three shapes, and each new
kind was about to invent a fourth.

The question also has an identity half. A scope is only enforceable where the
system knows **which agent is asking**. For the MCP gateway that is not
obvious: every agent reaches Coffer through the same stdio shim over the same
loopback daemon (see [stdio Shim Bridge](stdio-shim-bridge.md)), so the gateway
has to be told who is on the other end of each session.

## Options Considered

### Option A — one framework-owned allow-list of agent uids, enforced by each kind at its own choke point (chosen)

`Resource.scope` (`backend/coffer/domain/resource.py`) is one nullable value,
owned by the framework rather than by any kind's config:

```
scope == None                           → every agent
scope == {"agents": ["01J…<agent uid>"]} → that agent only
scope == {"agents": []}                 → dormant: matches nothing
```

One predicate, `is_active(scope, agent_uid)` in `backend/coffer/domain/scope.py`,
answers every question asked of it. A uid that names no registered agent is
legal and never matches, so a resource can be scoped to an agent this machine
does not have. An unidentified asker (`agent_uid=None`) matches only an
unrestricted scope — it sees strictly less, never more.

Each kind declares `supports_scope` on its `Kind` descriptor; a non-null scope
on a kind that declares none is refused with 422 (`validate_scope`). The value,
its validation and its one kind-agnostic write path
(`application/resource_scope_ops.py`, audited as `resource_scope_updated`) are
the framework's. **Enforcement is not**: each kind calls `is_active` at the
seam where it already knows the asking agent.

| Kind | Scope | Where it is enforced |
| --- | --- | --- |
| `mcp_server` | yes | The gateway session: `tools/list` / `resources/list` / `prompts/list` are built from the scope-filtered server list (`application/mcp/gateway_scope.py`), and the call seam re-checks before asking the supervisor for a connection (`application/mcp/gateway_handlers.py`), so a guessed `<server>__<tool>` name is refused as `TOOL_DISABLED` and logged as `denied`. Management routes (including the connection test) are not scope-gated. |
| `skill` | yes | Delivery: a skill reaches an agent iff it is `enabled` and `is_active(scope, agent)`; anything else is reclaimed (`application/skill/delivery_ops.py`). See [Cross-Platform Skill Delivery](cross-platform-skill-delivery.md). |
| `channel` | yes, **inverted** | A channel is consumed by no agent, so its scope names the agents it may *drive*; `/agent`, the default agent and adapter start all read it. See [Channel Owner Gate](channel-owner-gate.md). |
| `provider` | yes | Projection: a connection is written into the config of the agents its scope reaches (`application/provider/targets.py`); `compatible_agents` became this scope plus a `default_scope` pre-fill from the wire. See [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md). |
| `agent` | no | It *is* the agent; there is nothing for an agent scope to narrow. |
| `knowledge`, `memory` | no | Withdrawn 2026-09-18 (Option F). |

Pros: one shape and one predicate for every kind that has the question, so a
user who learns the control on MCP servers can use it on skills, channels and
connections; the identity plumbing is paid for once; each kind keeps its
enforcement next to the behaviour it gates, where the asking identity is
actually in hand. Cons: enforcement is only as complete as each kind's seams
(the MCP gateway needed a second check at the call seam after the listing
filter alone was found bypassable); and a kind whose scope has consequences
beyond filtering can have invariants between its config and its scope, which is
why the framework grew the `validate_scope_for` pre-write hook (see
[Kind Plugin Contract](kind-plugin-contract.md)).

### Option B — each kind keeps its own "which agents" field

The state before this decision: skills' follow flag + exclusions + per-binding
enable, providers' `compatible_agents`, and an MCP-only allow-list. Pros: each
kind can shape the answer to its own semantics. Cons: three kinds had already
diverged on the same question, and divergence was not cosmetic. Skills needed
three mechanisms to answer "does this agent get it"; `compatible_agents = null`
meant "the wire's default" while every other kind read null as "everyone", so
the provider migration (0071) had to materialise every row's effective set
rather than rename the field, or every never-narrowed connection would have
widened. Lost: the next kind would diverge again, and the UI could not offer one
control.

### Option C — deny-list ("every agent except these")

Pros: the common "hide from one agent" edit is one entry. Cons: a newly added
agent silently gains every restricted resource — the wrong default for a grant.
Lost on that default.

### Option D — one central gate in `ResourceService`

`ResourceService.get`/`list` would take the asking agent and filter. Pros: one
enforcement point instead of four. Cons: the service does not know who is
asking — a REST call from the UI, a CLI command, the skill reconciler and the
provider projection all read resources on no agent's behalf, and the management
surfaces must see every resource regardless of scope (an owner must be able to
test a server no session is allowed to use). The things scope actually gates
are four different acts — listing and routing MCP calls, placing a skill
directory, writing a provider into a config file, choosing which agent a chat
message drives — and each has its own asker. Lost: a central filter would
either be bypassed by every administrative path or break them.

### Option E — a machine × agent matrix inside the scope

The scope shipped as a machine × agent matrix in PR #296 (2026-07) and returned
as a second `AND`-ed machine allow-list in PR #381 (2026-09-14), removed the
next day in PR #382 (migration 0076 resolved each row against the machine it
was on, taking dormant when unsure). Lost because reach does not travel between
machines at all; argued in
[Resource Reach Is Machine-Local](resource-reach-is-machine-local.md).

### Option F — scope on every kind, `knowledge` and `memory` included

Both had `supports_scope` at times. Withdrawn in PR #404 (migration 0088 NULLs
their `scope_json`) because for those two kinds scope withheld a *name* and
nothing else: both serve files on disk that the agent is handed the path of,
enforcement sat only on the MCP tool surface, and the skill knowledge delivers
tells the agent to grep the whole root. The vault bore it out — every
`knowledge` row's scope was `NULL` for the field's whole life, while every
`memory` row carried an auto-default nobody chose, which hid the Coffer
project's memory from Codex sessions in that repository. Lost: a control the
system's own instructions route around is not a boundary, and removing it
widened reach on purpose.

### Option G — the allow-list holds agent names

The list held names until PR #406. Renaming an agent silently emptied every
scope naming it, and the channel kind carried a translation module because its
`default_agent` and its scope named agents in two vocabularies. Lost: a scope
is a reference to another resource, and references hold the immutable uid
(migration 0096; see
[Resource Identity Is an Immutable uid](resource-identity-is-an-immutable-uid.md)).

### How the gateway learns the asking agent

**Self-reported identity at the handshake (chosen).** The Coffer-MCP install
writes `coffer-mcp-shim --agent-uid <uid>` into each managed agent's native MCP
config; the shim stamps `params._meta["coffer/agent-uid"]` onto `initialize`
(`surfaces/shim/bootstrap.py`), and the gateway reads it once per session
(`application/mcp/gateway_parsing.py`) and uses it for every list and call.
Built-in tool calls get the session identity overwritten into their `agent`
argument, so a client cannot pick a different identity per call. A shim with no
flag — hand-configured, or an older entry carrying the name-based
`--agent` (deliberately not accepted: `allow_abbrev=False`) — is unidentified
and sees only unscoped servers. Pros: zero secrets to issue, rotate or store;
works with any MCP client that can launch a command. Cons: any local process
that can open the loopback MCP connection can claim any uid. That boundary is
stated in the spec rather than implied away, and it is acceptable because
Coffer's posture is single-user and loopback-only
([Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md)).

**Verified identity — a signed per-agent token.** Coffer would mint a token
per agent and write it into the same config entry; the gateway would verify it.
Pros: an unmodified *other* client could not impersonate an agent without the
token. Cons: the token would live in the agent's own config file, readable by
every process running as the same user — exactly the processes the check would
be defending against — so it would add rotation and storage machinery without
moving the trust boundary. Lost: under a single-user, same-UID threat model it
is ceremony, and scope is a relevance filter between the user's own agents,
not an isolation boundary between mutually distrusting principals.

## Decision

A resource's per-agent scope is one framework-owned, nullable allow-list of
agent **uids** on `Resource`: `None` is every agent, `[]` is dormant, and
`is_active(scope, agent_uid)` is the only predicate. Each kind declares
`supports_scope`; `mcp_server`, `skill`, `channel` and `provider` do, and
`agent`, `knowledge` and `memory` do not. The framework owns the value, its
validation and its audited write path; each kind enforces it at its own choke
point where the asking agent is known. The gateway learns the asking agent from
the shim's self-reported `coffer/agent-uid` handshake key, and an unidentified
session matches only unrestricted resources.

Rules a future change must respect:

- A kind that grows a "which agents" question declares `supports_scope`; it
  does not add a field of its own.
- Enforcement never widens on missing identity: `agent_uid=None` sees only
  `scope=None`.
- Scope entries are uids, never names.
- Administrative surfaces are not scope-gated.

## Consequences

- The gateway's tool listing is identity-dependent: one server can present
  different tool sets to different sessions at the same time.
- Scoping a skill out reclaims an already-delivered copy, so a scope edit has
  filesystem effects; it is audited like any delivery change.
- For `channel` and `provider` dormant means *off* — a channel that may drive
  no agent does not start its adapter; a connection that reaches no agent is
  projected nowhere. Dormant is still not disabled: the row stays visible and
  editable, and surfaces label it as "no agent selected", not "disabled".
- Because `channel` pre-validates scope writes against its `default_agent`, a
  narrowing can be refused, and the user occasionally needs two edits in order.
  What that buys is that stopping a channel is always explicit.
- The identity is only as trustworthy as the loopback posture; if Coffer ever
  serves a remote or multi-user client, Option "verified identity" must be
  revisited.
- Where scope applies — on which machine — is the subject of
  [Resource Reach Is Machine-Local](resource-reach-is-machine-local.md).
