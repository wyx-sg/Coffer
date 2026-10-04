## Why

Every hand-off in the web UI is the shared split button **Ask an agent ▾** with Copy prompt behind
its chevron (Foundations 0.7.04), except the Agents area: an agent whose program is not on this
Mac offered Copy prompt and Ask an agent at the top of its ⋯ menu, on the list row and in the
detail page's header.

## What Changes

- An Agents list row of an agent that is not installed, or whose config is left behind, shows the
  split button before its ⋯; the ⋯ menu no longer holds Copy prompt or Ask an agent.
- The agent detail page's header ⋯ no longer holds them either; the page body (not added, config
  left behind, not found) already shows the split button.
- The Channels status banner uses the shared split button in place of its own copy of it.

## Impact

- Frontend: `components/agents/list/` (`useAgentRowActions`, `AgentRowCells`),
  `components/channel/ChannelStatusBanner.tsx`; `HandoffSplit` and its string are deleted.
- Backend: none.
- Specs: agent-registry, web-ui.
- Docs: guides/agents (en + zh). Canvas: 2 Agents.
