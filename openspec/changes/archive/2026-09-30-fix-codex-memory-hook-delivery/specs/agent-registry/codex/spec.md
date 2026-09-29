## MODIFIED Requirements

### Requirement: Read Codex's hooks from hooks.json
The hooks of [agent-registry](../spec.md) "List every hook in the agent's native config" MUST be read, for `codex`, from two places: the config directory's `hooks.json` (source `user`), and the `hooks/hooks.json` of each enabled installed plugin, where one exists. `hooks.json` is the file Codex's hooks feature reads, in the same event-keyed shape as Claude Code's. Coffer's own delivery hook sits on `SessionStart` in `hooks.json`, with the matcher `startup|resume|clear|compact`.

#### Scenario: read Codex hooks from hooks.json
- **GIVEN** a Codex agent whose `hooks.json` carries Coffer's marked hook
- **WHEN** the user lists its hooks
- **THEN** the hook is listed from `hooks.json` with source `user` and marked as Coffer's

## ADDED Requirements

### Requirement: Report whether Codex will run Coffer's hook
Codex runs a non-managed hook only after the user has approved its exact definition in `/hooks`, and it silently skips one it has no approval for. For `codex`, the trust that "List every hook in the agent's native config" reports MUST therefore be read from Codex's own approval record: `config.toml`'s `[hooks.state."<hooks.json path>:<event>:<group>:<handler>"]` table.

Coffer computes the hash of its entry the way Codex does. The trust is:
- `trusted` when `trusted_hash` equals that hash;
- `modified` when it records another hash;
- `untrusted` when no approval is recorded for that position;
- `disabled` when `enabled = false`;
- `unknown` when `config.toml` does not parse.

Reading it MUST NOT write `config.toml`. Coffer MUST NOT record an approval of its own, because approving a hook is the user's review, and "Leave Codex's internal-state tables untouched" keeps `[hooks.state.*]` byte-identical.

#### Scenario: report whether Codex trusts Coffer's hook
- **GIVEN** a registered Codex agent whose `hooks.json` carries Coffer's current hook on `SessionStart`, and whose `config.toml` records no approval for it
- **WHEN** the user lists its hooks, then approves the hook in Codex, then a later build changes the command
- **THEN** Coffer's hook reads `untrusted`, then `trusted`, then `modified`, and `coffer agent hooks` tells the user to run `/hooks` in Codex while it is not trusted
- **AND** `config.toml` is exactly as Codex left it after every read
