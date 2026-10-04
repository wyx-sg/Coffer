## Why

An agent had two ways to stop being touched by Coffer: Disconnect, which takes
Coffer's entry and hook out of its config, and a kind-agnostic on/off switch. The
switch left the agent registered and visible but ignored, and every consumer of an
agent — skill delivery, memory aggregation, the model catalogue, chat, provider
projection, attention — carried a branch for "registered but off". Two off-states
beside Not connected also made the Agents page harder to read: a row could read Off,
Not connected or Needs repair, and each asked for a different action.

An agent is either connected to Coffer or it is not. Connect and Disconnect are the
whole control.

## What Changes

- **BREAKING** The `agent` kind is non-toggleable, like `knowledge` and `memory`.
  `POST /api/v1/resources/{uid}/enable|disable` answers an agent with 409
  `RESOURCE_NOT_TOGGLEABLE`, and the agent's resource always reads enabled. An agent
  stored as switched off before this change reads enabled from then on.
- The agent kind has no enabled reaction: the skill reclaim that ran when an agent
  was switched off is gone, and so is every "skip a disabled agent" branch in skill
  delivery, memory aggregation, the model catalogue, chat, provider projection and
  the attention list. Each of them works from the registered agents.
- The Agents page has no Off state: no Off pill, no Turn on button, no Turn off menu
  item, no switch-off pending state. A row is Connected, Not connected, Needs repair,
  Hook not approved, Config left behind or Not found.
- The adoption exception for a disabled agent ("Adopt an unmanaged skill") goes with
  the switch; the requirement returns as "Adopt an unmanaged skill into the master
  store". "Read only registered and enabled agents' memory" becomes "Read only
  registered agents' memory", and "Ship Claude Code and Codex subprocess providers on
  the type's one agent" becomes "Run Claude Code and Codex as subprocess providers on
  the type's one agent".
- The wording of `PROVIDER_DOES_NOT_REACH_AGENT` names the connection only: it is
  refused when the connection is switched off or its scope does not name the agent.
- The guides, architecture pages, glossary, error-code reference and the ADRs that
  described switching an agent off say disconnect instead.

## Capabilities

### Modified Capabilities

- `agent-registry`: the lifecycle, audit, Agents page, Coffer connection, model
  catalogue and install hand-off requirements lose the off state; the requirement
  "Switch an agent off with the kind-agnostic enabled flag" is removed. The
  `claude-code` and `codex` children follow the renamed chat requirement.
- `skill-manager`: delivery, adoption, reconcile, the Delivery tab and the reach
  report work from registered agents.
- `memory`: aggregation reads every registered agent.
- `chat`: a turn runs against the type's registered agent.
- `provider-switching`: switching, drift clearing and reverting name the agent
  without an enabled condition.
- `resource-framework`: `agent` joins `knowledge` and `memory` as a non-toggleable
  kind, and a stored off-state of such a kind reads enabled.

## Impact

- Backend: the agent kind declares `toggleable=False` and drops `on_enabled_changed`;
  the resource store reads a non-toggleable kind's resource as enabled.
- Frontend: the Agents list and detail pages lose the Off state and its actions;
  the matching i18n keys are deleted in English and Chinese.
- Docs: `docs-site` (English and Chinese), `docs/decisions`.
