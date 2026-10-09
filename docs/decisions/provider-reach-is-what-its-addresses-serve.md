# A Connection Reaches the Agents Its Addresses Serve; No Scope, No Off Switch

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [One Connection Serves Both Wires: an Optional Anthropic Address Beside the Base URL](one-connection-serves-both-wires.md), [Per-Agent Resource Scope Is One Framework Allow-List, Enforced by Each Kind](per-agent-resource-scope.md), [Reach Is Machine-Local: Stored by uid in `local/reach.json`, Never Synced](reach-is-machine-local-stored-by-uid-never-synced.md), spec provider-switching "Derive the agents a connection serves from its addresses", spec provider-switching "Retire the off switch and scope of existing connections", spec provider-switching "Keep an agent on at most one connection"

## Context

A `provider` connection used to carry two framework controls:

- the per-agent scope, which named the agents it might serve;
- the enabled switch.

Both were edited in the shared reach control on the connection's header. Both
predate two other facts:

- **Which connection an agent runs on** is a field of the agent record
  (`AgentConfig.connection_uid`), chosen in the agent's Change model dialog.
- **Which agents a connection can serve** follows from its addresses
  ([one-connection-serves-both-wires](one-connection-serves-both-wires.md)).
  Claude Code needs an Anthropic address and Codex an OpenAI one.

With both in place, the user asked whether the scope and the agents a provider
supports could conflict. They can: a scope could name Claude Code on a
connection with no Anthropic address, which is the DeepSeek incident. The user
then asked to drop the scope: "我感觉model provider的reach可以删除掉，不需要设置可用范围。只显示这个model provider支持哪个agent就好". On the follow-up card about
the off switch, the user chose to drop it too.

How comparable tools handle it:

- **cc-switch** keeps a list of providers per app and makes one of them active
  per app. Which app a provider is for is fixed by the list it sits in; there
  is no per-provider filter on top.
- **Cline and Roo Code** pick an API configuration (profile) for the session or
  mode. Nothing on a provider restricts who may use it.
- **opencode** lists the models of every configured provider in its picker.

## Options Considered

### Option A — Reach is what the addresses serve; no scope, no off switch (chosen)

- **Pros:**
  - One fact decides whether a connection serves an agent, and it is the one
    that decides whether the agent's requests can work.
  - Nothing on the connection's page to keep in agreement with the agent's own
    choice.
  - Matches how comparable tools work.
- **Cons:**
  - A connection can't be parked: one you don't want offered is deleted.
  - Agents on a connection that was switched off have to be moved before the
    switch goes, or turning it on would quietly re-route them. A startup
    migration does this.
- **Why it wins:** the agent already chooses its connection, so a second
  per-connection filter only adds a way to contradict that choice.

### Option B — Keep the scope, limited to the agents the addresses serve

The scope can select only served agents. Unsupported ones show greyed out with
a reason. This was the first answer the user chose, before deciding the scope
itself was unnecessary.

- **Pros:** someone can hide a connection from one agent's picker.
- **Cons:**
  - Two controls for one question.
  - The scope still says nothing the agent's own choice doesn't.
- **Why it loses:** it keeps a control whose only job is narrowing a picker
  that already lists a handful of connections.

### Option C — Drop the scope, keep the off switch

- **Pros:**
  - A connection can be parked without deleting it.
  - No migration of switched-off connections.
- **Cons:**
  - A switch whose only effect is hiding the connection from pickers and taking
    agents off it.
  - Taking an agent off is already the agent's revert.
- **Why it loses:** the user chose to drop it on the decision card.

### Option D — Keep both as they were

- **Pros:** no change.
- **Cons:** the scope can contradict the addresses, which is how Claude Code
  ended up routed to an endpoint with no Messages API.
- **Why it loses:** it leaves the conflict the user asked about.

## Decision

A connection serves exactly the agents whose wire it has an address for, and
every read reports them as `served_agents` (`compatible_agents` is the same
list). The `provider` kind declares no scope. No surface offers it an off
switch. A scope stored before this rule is ignored.

At startup, before the boot reconcile pass:

- every agent on a switched-off connection goes back to its own login;
- that connection is switched on;
- stored scopes are cleared.

The kind declares its switch retired: the generic disable route refuses a
connection, but the stored flag stays readable so this step can find the
connections that were off. A later release makes the kind non-toggleable and
deletes the step.

Rules that follow:

- A refused switch says which address is missing ("add its Anthropic address"
  for Claude Code), not that a scope excludes the agent.
- The agent's Change model dialog offers the connections that serve it.

## Consequences

- `scoped_targets` and `reaches` in `backend/coffer/application/provider/targets.py`
  read the addresses (`serves`, `served_agents`). `connection_for_agent` follows
  them.
- `application/provider/reach_retirement.py` is the startup step. Its
  `migrate_saved_connections` runs it, then the Anthropic-address fill, from
  `surfaces/http/app.py`.
- `provider/kind.py`: `supports_scope=False`. A scope PUT on a connection is
  refused.
- The connection's header (`ProviderDetailHeader.tsx`) says "For Claude Code,
  Codex" in place of the reach control.
- The [per-agent scope ADR](per-agent-resource-scope.md) still governs the
  kinds that declare a scope; providers no longer do.
