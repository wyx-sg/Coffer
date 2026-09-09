# ADR-046: Budget-Driven Tool Tiering at the Gateway

> 中文版: [ADR-046-budget-driven-tool-tiering.zh.md](ADR-046-budget-driven-tool-tiering.zh.md)

**Status**: Accepted
**Date**: 2026-09-09
**Deciders**: Yuxing Wu
**Amends**: [ADR-018](ADR-018-tool-retrieval-for-overload.md) — the "nothing is
hidden server-side" clause is replaced by budget-driven tiering
**Related**: [ADR-024](ADR-024-builtin-agent-is-internal-capability.md)
(semantic ranking), [ADR-045](ADR-045-machine-agent-resource-scope.md)
(machine × agent scope), [ADR-004](ADR-004-capability-state-model.md)
(capability preferences), reverted [ADR-026](ADR-026-per-agent-mcp-scoping.md)
(per-agent scoping), [spec `001-mcp-gateway`](../../specs/001-mcp-gateway/spec.md),
[`docs/research/mcp-ecosystem.md`](../research/mcp-ecosystem.md)

## Context

ADR-018 shipped `coffer__search_tools` as the answer to aggregation overload and
made one explicit bet:

> **Additive.** Coffer continues to advertise the full upstream catalogue exactly
> as before; nothing is hidden server-side. Tool deferral, if any, stays the
> client's choice.

That bet has been falsified in production use. Measured on this vault:

| Signal | Value |
| --- | --- |
| Upstream tools discovered across registered servers | 316 |
| Upstream tools reaching one live Claude Code session | ~125 |
| Distinct tools ever invoked (all history) | 44 |
| `mcp.gateway.list_tools.upstream_failed` events in one log rotation | 180 |

Two things went wrong.

**The client's deferral is indiscriminate.** Handed ~125 tools from one server,
Claude Code moved the entire `mcp__coffer__*` namespace behind its own
tool-search indirection — **including `coffer__search_tools` itself**. ADR-018's
escape hatch ended up locked behind the same door it was built to open. Leaving
the decision to the client assumed the client would defer *selectively*; it does
not, and it cannot, because it has no usage signal to defer on. Coffer does.

**Nothing told the agent Coffer existed.** The gateway's `initialize` reply
carries no MCP `instructions` field, so no client ever received a
system-prompt-level statement of what Coffer is or that `search_tools` should be
called first. ADR-018's contract was documented for humans and never delivered
to the agent that had to follow it.

ADR-018's own research is the calibration: agent tool-selection accuracy falls
off sharply past **30–50 tools**. Coffer was serving two-to-four times that and
relying on the client to fix it.

Prior art matters here. [ADR-026](ADR-026-per-agent-mcp-scoping.md) built
per-agent server scoping and was reverted as over-complex; the field's
"strategy 1" (ContextForge virtual servers, MetaMCP namespaces, MCPJungle tool
groups, Docker profiles) all require the user to curate a subset by hand.
[ADR-045](ADR-045-machine-agent-resource-scope.md) has since restored a
machine × agent `scope` axis, but it gates whole servers and, like every
manual scheme, does nothing until configured. The default install is where the
overload actually bites.

## Decision

**The gateway lists a budgeted slice of the aggregated catalogue instead of all
of it. The slice is computed from real invocation history, requires no user
configuration, and hides nothing that cannot still be called.**

Four parts.

### 1. Tiering policy

A pure function over (aggregated tools, per-tool usage counts):

- Coffer's own `coffer__*` built-ins and `search_tools` are **always** listed.
- `budget` (**default 50**, from ADR-018's own 30–50 finding) counts **upstream
  tools only**; the always-listed built-ins sit on top of it.
- If the upstream tool count is at or under `budget`, every tool is listed —
  today's behavior exactly.
- Over budget: rank upstream tools by invocation count within a trailing window
  (**default 90 days**), take the top of the list, then round-robin by server to
  fill the remainder, with a **floor of one tool per enabled server** so no
  server becomes wholly invisible.
- Within a server, unused tools are drawn in the server's own `tools/list` order,
  so the selection is deterministic and stable across sessions for an unchanged
  catalogue. Ties in invocation count likewise keep catalogue order.
- Everything else is unlisted.

### 2. Hidden is not disabled

Unlisted tools remain fully callable. `tools/call` gates on
`mcp_capability_preferences.enabled` ([ADR-004](ADR-004-capability-state-model.md)),
never on list membership, and `search_tools` continues to rank the **full**
catalogue. A tool leaves the list; it never leaves the gateway. This is the
clause that makes tiering safe to enable by default and distinguishes it from
the manual allowlists of strategy 1.

### 3. The contract is delivered to the agent

`initialize` returns an MCP `instructions` string stating what Coffer is, that
frequently-used tools are listed directly, and that `search_tools` reaches the
rest. It is generated per session so it can name the actual number of unlisted
tools, and is capped (~800 characters) because it lands in every session's
system prompt — the context it spends must stay far below the context tiering
saves.

### 4. Degradation is recoverable, not silent

A per-server discovery timeout currently drops that server's entire tool list
for the life of the session: the client caches `tools/list`, and no
`notifications/tools/list_changed` can arrive because the server never
connected. Instead, a failed server is recorded as degraded, retried in the
background, and on recovery the gateway invalidates the cache and emits
`notifications/tools/list_changed` so the client re-lists mid-session. The 5 s
per-server budget is unchanged — the defect was irrecoverability, not the
threshold. Failure logs gain the server name and error, which the current
`extra`-based call site never renders.

**Escape hatch.** A `mode: auto | off` setting; `off` restores ADR-018's
semantics exactly. If the usage-statistics query fails, tiering degrades to
listing everything — a broken statistics layer must never be able to make tools
disappear.

## Consequences

**Positive**

- **The default install stops overloading the client.** The listed upstream
  slice drops from ~125 to at most `budget`; with Coffer's own built-ins always
  on top, a session lists roughly 50 + 17 ≈ 67 tools instead of ~142, and the
  upstream slice sits inside ADR-018's 30–50 accuracy band. Whether that clears
  any particular client's deferral threshold is not something Coffer can know —
  the claim here is only that it is far below what is served today.
- **The escape hatch becomes reachable.** `search_tools` and the `coffer__*`
  built-ins are pinned into the listed slice by construction.
- **Cold start is safe.** A fresh vault has no invocation history but also few
  tools, so it takes the under-budget branch and sees everything. Usage history
  only matters once there is enough of it to matter.
- **Recoverable degradation.** A slow cold spawn costs one list round-trip
  instead of a whole session's access to that server.
- **Coffer gains strategy 1 without ADR-026's cost.** The subset is curated by
  observed behavior rather than by the user, which is precisely the manual step
  that made ADR-026 not worth its complexity.

**Negative**

- **Listing is no longer a pure reflection of upstream.** `tools/list` becomes
  policy-dependent, so "why can't the agent see tool X" now has one more layer
  to check. Mitigated by `mode: off` and by surfacing the unlisted count in
  `instructions`.
- **Usage history is self-reinforcing.** A tool never called ranks low and stays
  unlisted, so it stays uncalled. The per-server floor and `search_tools` over
  the full catalogue are the counterweights, but the bias is real and a
  genuinely new tool on a busy server is discoverable only through search.
- **Tiering needs a usage query on the `tools/list` path.** A hot path gains a
  DB read; it is a single indexed aggregate over `mcp_invocations` and degrades
  to "list everything" on failure.

## Alternatives Considered

**Keep ADR-018 unchanged; rely on client deferral.** Rejected: this is the
option that was measured and failed. The client folded away the very tool ADR-018
added, and it has no signal with which to choose better.

**Manual per-agent allowlists only (strategy 1 as the field does it, or
extending ADR-045's agent axis to tool granularity).** Rejected as the primary
mechanism: it does nothing until configured, and the unconfigured default is
exactly where the failure occurs. ADR-026 already demonstrated that hand-curated
scoping is not worth its complexity here. ADR-045's server-level axis remains
available and composes with tiering — scope decides which servers a session
sees, tiering decides which of their tools get listed.

**Hide all upstream tools; force every call through `search_tools`.** Rejected:
it breaks direct invocation of the tools an agent uses constantly, spending a
search round-trip on every routine `jira_get_issue`. The measured 44
regularly-used tools are precisely the ones that should stay one call away.

**Raise the per-server discovery timeout.** Rejected as the fix for part 4: the
5 s budget exists so one dead upstream cannot stall the aggregate list, and the
parallel fan-out rationale still holds. Recovery, not a larger threshold, is
what the failure mode calls for.
