## MODIFIED Requirements

### Requirement: Hand an agent's missing program to an agent on the agent pages
Wherever the web UI shows an agent type whose program is not found — its Agents list row, its detail page while it is not added, and the
Overview tab's problem states (config left behind, not found) — it MUST offer the daemon's
`install_handoff` prompt for that type (agent-registry "Hand installing an agent's program to an
agent") through the hand-off split button of "Hand a machine-dependent problem to an agent with one split
button", whose Ask an agent is offered only while another managed agent is available to run the
conversation: the missing agent itself cannot. On a list row the split button sits before the row's ⋯
menu, which holds neither Copy prompt nor Ask an agent, and the detail page's header ⋯ holds
neither. None
of these surfaces MUST show an install command or tell the person to restart Coffer. The
Plugins tab of a Claude Code agent whose program is not found, where Uninstall cannot run, MUST
say so and offer the same prompt. The Connect review MUST offer the hand-off a `SHIM_NOT_FOUND`
refusal carries beside Retry (agent-registry "Install Coffer's MCP server into an agent in one
action").

#### Scenario: an agent whose program is not found offers its install prompt
- **GIVEN** Codex not installed and no managed agent available
- **WHEN** the user presses Copy prompt on the Codex row
- **THEN** the daemon's prompt is copied as given and no install command is shown anywhere
- **AND** the row offers no Ask an agent, and its ⋯ menu offers no Copy prompt

#### Scenario: ask an agent is offered only while another managed agent is available
- **GIVEN** Claude Code's config left behind with its program gone, and Codex available as a managed agent
- **WHEN** the user presses Ask an agent on the Claude Code row's split button
- **THEN** New conversation opens, and nothing is written or sent
- **AND** with only Claude Code itself managed, the row offers Copy prompt alone

#### Scenario: a connect refused for a missing shim offers the daemon's prompt
- **GIVEN** a registered agent and a daemon that refuses its Connect with `SHIM_NOT_FOUND` carrying a hand-off
- **WHEN** the user applies the Connect review
- **THEN** the review shows the change as failed with copy that names no environment variable or command
- **AND** Copy prompt beside Retry copies the refusal's prompt as given
