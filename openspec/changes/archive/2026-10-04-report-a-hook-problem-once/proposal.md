## Why

When Codex has not approved Coffer's memory hook, Overview's "Needs you" list
shows it twice for the same agent: the reconciler's memory-hook target reports
`hook_untrusted` ("open Codex, run /hooks and trust Coffer's hook"), and the
agent kind's source reports `agent_hook_attention` ("It has not approved
Coffer's memory hook") from the same trust record.

## What Changes

- The agent kind's `agent_hook_attention` item covers only a hook the agent
  runs (no review step, or trusted for this definition) that has never fired.
- A hook the agent will not run — unapproved, approved for an earlier command,
  switched off, an unreadable trust record — is reported once, by the
  reconciler's memory-hook target (`hook_untrusted`, `hook_disabled`,
  `hook_trust_unknown`), whose item opens the agent's Hooks tab.

## Capabilities

### Modified Capabilities
- `agent-registry`: "Report an agent whose Coffer hook needs the person" becomes "Report an agent whose Coffer hook never fires" and narrows to that case; "List the supported agents as fixed rows on the Agents page" cites it under the new name.

## Impact

`application/agent/attention.py` and its unit tests; docs-site guides/agents (en + zh).
