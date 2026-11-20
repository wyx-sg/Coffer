# Add Antigravity as a third agent type

## Why

The owner uses Google Antigravity (its desktop App, its `agy` CLI and its IDE) beside Claude Code and Codex, and Coffer's job is to serve every agent the person uses from one MCP endpoint and one skill library. Antigravity documents one personal config layer, `~/.gemini/config/`, that all three of its surfaces read.

## What Changes

- New agent type `antigravity` with standard config directory `~/.gemini/config`, program `agy` and app bundle `Antigravity.app`.
- Coffer's MCP entry is written into `mcp_config.json` (JSON `mcpServers`, with a 24-hour `timeoutSeconds`); skills are linked into `~/.gemini/config/skills/`; a five-entry config-file allowlist.
- Detection accepts an app bundle when the program is not on the `PATH`, so an App-only install reads installed.
- No provider projection, driver, memory reader or session source for Antigravity, and why (ADR antigravity-joins-at-its-config-layer-only).
- The Agents page lists three rows; its first-run action becomes **Connect all**, offered when no agent is connected and at least two are connectable.
- The requirement "Support exactly the Claude Code and Codex agent types" is renamed for three types and allows a type to lack a mechanism facet its product cannot provide.

## Impact

- Specs: agent-registry (renamed and modified requirements), new child agent-registry/antigravity.
- Code: `domain/agent` (type, descriptor, allowlist), `infrastructure/platform/apps.py`, the program probe, the facet wiring; the frontend's agent helpers and Agents page.
- Docs: Agents guide and agent facets architecture page (English and Chinese), ADR, `docs/TODO.md`.
