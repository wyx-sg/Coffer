## Why

A resource had two ways to reach no agent: switch it off, or leave it on with
its reach set to "Chosen agents" and nothing ticked (`scope = {"agents": []}`,
called dormant). Both do the same thing — nobody gets the resource — but they
read differently. A dormant MCP server sits under "Healthy" with a green dot and
"No agent selected" beside it, so the list says it is in use when it is not.
Channels went further and used dormant as a second off, with its own runtime
branch and its own spec rules, although a channel already has the same on/off
switch as every other kind.

A resource is either off, or on for every agent, or on for the agents chosen.
Off is the one way to reach nobody.

## What Changes

- **BREAKING** `scope = {"agents": []}` is no longer a valid scope on any kind.
  `PUT /api/v1/resources/{uid}/scope` answers it with 422 `SCOPE_INVALID`, and so
  does every other write that carries a scope: creating a custom-tool group,
  adopting an unmanaged skill with chosen agents, importing MCP servers.
- A one-time startup step rewrites every reach record holding an empty agent list
  to `enabled: false` with an unscoped reach, so turning such a resource on gives
  it to every agent. The step is removed in a later release once it has run.
- Provider: the `ollama` connection no longer starts dormant; `default_scope` and
  `starts_dormant` are deleted (`ollama` already projects to no agent).
- Channel: dormant is gone. A channel that should drive nothing is switched off,
  and a switched-off channel stays editable, as it already is. The scope
  validator refuses an empty list like every other kind.
- Web UI: the reach panel's "Chosen agents" list cannot be emptied — the last
  ticked agent cannot be unticked, and the panel says to turn the resource off
  instead. Switching to "Chosen agents" saves nothing until one agent is ticked.
  Add, adopt, import and custom-group dialogs refuse "Chosen agents" with none
  ticked. A bulk change that would untick every agent on a row switches that row
  off. The "No agent selected" label and the dormant warning are deleted.
- Specs, architecture pages, guides (en + zh) and ADRs that described dormant say
  off instead.

## Capabilities

### Modified Capabilities

- `resource-framework` — "Carry a per-agent reach on every resource": scope is
  `null` or a non-empty agent list.
- `vault-sync` — "Scope names agents only": no dormant value.
- `skill-manager` — "Deliver a skill only where it is enabled and in scope".
- `provider-switching` — "Switch one agent at a time": no dormant default.
- `channels` — "Limit the agents a channel may drive to its scope".
- `web-ui` — "Show reach as one button that names it", "Offer reach as one choice
  in a panel", "Save the reach on every change", "Apply reach to a whole selection".

## Impact

- Backend: `domain/scope.py`, `application/resource_scope_ops.py`,
  `application/channel/{kind,wanted}.py`, `application/provider/kind.py`,
  `domain/provider/config.py`, `application/mcp/custom_tools.py`,
  `application/skill/unmanaged_ops.py`, `infrastructure/vault/reach_store.py`,
  `surfaces/http/app.py`, schema docstrings and the generated OpenAPI/TS types.
- Frontend: reach components and every draft reach picker; i18n `scope.*`.
- No database migration: reach lives in the machine-local `reach.json`.
