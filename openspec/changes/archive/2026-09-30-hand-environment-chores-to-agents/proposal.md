## Why

Principle IV (AI-Native) says a chore that depends on the person's machine — installing a
program, setting up a tool, diagnosing the environment — is handed to an agent with a prompt the
daemon writes, not scripted by the product. An audit of the app found the opposite in many
places: npm install commands for the two agents, a Homebrew table for MCP launchers, a manual
unpack procedure for the SeaTalk SDK, `coffer config set` and `coffer daemon restart` lines to
copy, remedy strings naming `coffer skill verify --fix`, and flows (a skill update clashing with
local edits, a refused curation-pass undo, skills still reading a plaintext secrets file) that
leave the person alone with a binary choice or "do it by hand". Commands written into backend
reason strings also reached the Overview verbatim.

## What Changes

- **One hand-off everywhere.** Each feature builds its prompt with `domain/handoff.py` from facts
  it already has and serves it as `handoff: {prompt}` on the response its page reads; the CLI
  prints the same text. The web UI shows it with `AgentHandoff` (Copy prompt, and Ask an agent
  while a managed agent is available — so copy only when none is).
- **The attention list carries it.** `AttentionItem` gains an optional `handoff`; reasons name no
  command; the Overview row offers Copy prompt / Ask an agent in its ⋯ menu; `coffer attention
  --prompt <key>` prints it.
- **Agents.** The hard-coded npm commands are gone from the Agents list, detail and Overview
  cards; `GET /agents/types` and `GET /agents/{uid}` carry a per-type install or reinstall prompt
  (`install_handoff`) that keeps the existing config folder, names the program and the PATH Coffer
  looks it up on, and leaves the login to the person; `coffer agent prompt <type>` prints it. A
  missing `coffer-mcp-shim` refusal carries a prompt in its error details, and every CLI refusal
  that carries one prints it. Program lookups for plugins and conversations use the agent's real
  `PATH`.
- **Conversations with no managed agent** offer the install-an-agent prompt to copy, or a link to
  the Agents page once an agent is installed.
- **MCP servers.** The Homebrew table is gone: a missing launcher carries a prompt naming the
  launcher, the server and its command line; a failing server or failed test carries a diagnose
  prompt with the config summary (secrets redacted), the last stderr lines and the error, beside
  Test and View log. `coffer mcp handoff` and `coffer mcp test --prompt` print them.
- **SeaTalk SDK missing.** The banner hands unpacking and checking the SDK to an agent; the portal
  download stays with the person. The docs keep the manual steps.
- **Experimental feature off.** The gate has a Switch on button (the Settings toggle's route), or
  explains a `COFFER_FEATURES` pin.
- **Daemon.** `POST /daemon/restart` restarts the daemon from a browser by starting a successor
  that binds once this daemon has exited; `GET /daemon/upgrade` hands an upgrade to an agent.
- **Skills.** Drift reports carry no remedy text (the UI says "Repair puts it back"; the CLI keeps
  its own words); a folder in the way, an orphan master and a missing master carry prompts beside
  the manual buttons; an update clashing with local edits offers "Merge with an agent" and then an
  explicit, audited **I merged it** (`POST /skills/{uid}/source/merged`, `coffer skill update
  --merged`) that moves the pin forward without touching the files; a Git import on a machine
  with no git hands installing it to an agent.
- **Secrets.** Skills still reading `~/.coffer/secrets/` are handed to an agent to rewrite, by
  file and line only — never a value.
- **Model providers and usage.** No local runtime found hands setting one up to an agent; the
  quota card hands the statusline wrapper to an agent.
- **Knowledge.** A refused curation-pass undo carries a prompt for undoing it by hand; history on
  a machine with no git hands installing it to an agent.

## Impact

- Specs: resource-framework, agent-registry, mcp-gateway, skill-manager, secret,
  channels/seatalk, experimental-features, daemon, provider-switching, knowledge, web-ui; and, in
  place, the unarchived `revise-web-ui-ia` deltas it touches (Overview, agent rows, the draft
  conversation, the daemon tab and port, the desktop frontend).
- Wire: new `handoff` fields, `POST /daemon/restart`, `GET /daemon/upgrade`,
  `POST /skills/{uid}/source/merged`; `DriftEntryOut.suggested_remedy` removed. Audit events
  `skill_update_merged`, `daemon_restarted`. Error `SKILL_UPDATE_NOT_PENDING`.
- CLI: `coffer attention --prompt`, `coffer agent prompt`, `coffer mcp handoff`,
  `coffer mcp test --prompt`, `coffer skill verify --prompt`, `coffer skill update --prompt` /
  `--merged`, `coffer secret scan --prompt`, `coffer usage quota --prompt`.
- `usage_routes` now reads the agent registry for Claude Code's config folder.
