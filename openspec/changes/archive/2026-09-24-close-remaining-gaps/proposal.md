## Why

The drift audit left the last gaps between what the specs promise and what the
code does: management operations reachable over REST but not the CLI, an
agent's own config directory ignored whenever Coffer runs or queries that agent,
two machines unable to agree on one internal-engine default, and a machine with
no master key unable to say which credentials it cannot read.

## What Changes

- The CLI reaches every REST management operation it was missing:
  `coffer sync remote set --worktree`, `coffer mcp invocations` across every
  server, `coffer skill files|cat|write` and `coffer engine upkeep runs`. The
  Purpose sections that recorded those gaps no longer need to.
- A Claude Code agent with a custom config directory reads and writes
  `<config_dir>/.claude.json`, as Claude Code itself does.
- Turns, Codex's model listing and Claude Code plugin uninstall run against the
  agent's own config directory (`CLAUDE_CONFIG_DIR` / `CODEX_HOME`).
- A synced internal-engine default is settled by a tie-break every machine
  computes the same way — the smaller uid keeps the flag — so two machines that
  each set a different default converge on one.
- A machine with no master key reports every credential it holds ciphertext for
  as locked; a key that exists but cannot be read right now reports none.

## Capabilities

### New Capabilities

### Modified Capabilities

- `agent-registry`, `agent-registry/claude-code`, `agent-registry/codex`
- `chat`
- `provider-switching`
- `vault-sync`
- `mcp-gateway`
- `skill-manager`
- `resource-framework`
- `web-ui`

## Impact

CLI modules (sync remote, mcp invocations, skill files, engine upkeep), agent
config-dir resolution and the chat and Codex subprocess environments, the
provider sync normaliser, the master-key lookup and credential sync adapter, the
agent-registry contract and regenerated client, and the docs-site guides.
