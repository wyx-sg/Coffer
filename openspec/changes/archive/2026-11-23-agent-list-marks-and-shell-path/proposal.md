## Why

On the owner's Mac (2026-11-23) the Agents list showed a raw translation key in the Provider column for Cursor and Antigravity, the "config left behind" line ran under the row's hand-off button, the four new agents had no mark, and OpenCode and DeepSeek Harness, installed under nvm, read "not on PATH".

## What Changes

- The Provider line has words for every agent type on its own login (Cursor, Antigravity, DeepSeek Harness); a test keeps every type covered in both languages.
- On an Agents list row the hand-off split button reads **Ask an agent** (the agent's mark and tooltip still name who runs it), so it fits the Actions column.
- Cursor, OpenCode and Antigravity show their vendors' marks (LobeHub Icons, MIT), DeepSeek Harness the DeepSeek whale; monochrome marks invert on the dark theme.
- The user's `PATH` is asked of an interactive login shell (`$SHELL -ilc`), then a login-only one (`-lc`), in the daemon and the desktop app, with markers around the value. ADR `the-users-path-is-read-from-an-interactive-login-shell`.

## Capabilities

### Modified Capabilities

- `web-ui`: "Show an agent by its official mark" names the new marks; "Hand a machine-dependent problem to an agent with one split button" names the list row's label.
- `agent-registry`: "Detect an agent by its program and its config directory" asks an interactive login shell; new scenario "find a program a Node version manager installed".
- `daemon`: the login service's `PATH` comes from the same probe.

The main specs are edited directly, so this change carries no delta.

## Impact

Frontend agent marks and list cells, locales, the platform layer's `login_shell_path`, the desktop app's `env_path.rs`, tests, the docs-site agents guide and daemon architecture page (en and zh).
