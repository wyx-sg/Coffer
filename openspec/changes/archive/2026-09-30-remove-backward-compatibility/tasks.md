## 1. Agent configs

- [x] 1.1 Recognise only the `coffer proxy token` apiKeyHelper
- [x] 1.2 Delete the earlier Codex shell-exclusion cleanup (`codex_shell_env`)
- [x] 1.3 Stop deleting the retired Claude Code model env keys
- [x] 1.4 Reconcile each agent's MCP entry in its own file only
- [x] 1.5 Drop the older-build cases from memory-hook repair and trim the old `--agent` comments

## 2. Command line and REST

- [x] 2.1 Remove `coffer memory context` and list it in `check_removed_commands.py`
- [x] 2.2 Remove `POST /api/v1/memory/context`
- [x] 2.3 Treat a 404 from the approvals list as an error

## 3. Config and stored data

- [x] 3.1 Stop stripping `idle_shutdown_hours` from `daemon-config.json`
- [x] 3.2 Migration 0199 strips `idle_timeout_seconds`; `MCPServerConfig` forbids unknown keys
- [x] 3.3 Hyphen-only skill names
- [x] 3.4 Apply the 24-character MCP server name cap on every register and rename
- [x] 3.5 Drop the old alembic log-line parser
- [x] 3.6 Drop the in-place binary sentinel cleanup
- [x] 3.7 Require `login_service_supported` in the desktop tray watcher
- [x] 3.8 Give migration 0089 a frozen copy of the agent skill-dir lookup

## 4. Startup moves

- [x] 4.1 Remove the pre-0.2 keychain secret move
- [x] 4.2 Remove the signed build's master-key move
- [x] 4.3 Remove the auto-approval of bindings that existed before the secret boundary
- [x] 4.4 Remove the removed-agent-types notice

## 5. Web addresses

- [x] 5.1 Point the Overview and Activity links at current addresses
- [x] 5.2 Remove every old-route, old `?tab=`, tab-alias and old-uid redirect (except `/settings/sync`, which the vault/sync rework owns)

## 6. Docs

- [x] 6.1 docs-site, data-model files and generated references

## Note

The pinned OpenSpec CLI refuses a MODIFIED block that drops a scenario of the
current requirement, so the MODIFIED blocks here still carry the eight
scenarios this change deletes. They were removed from `openspec/specs/`
directly after archiving, with their acceptance markers:
provider-switching "every write deletes the deprecated background-model key"
and "a leftover shell exclude entry is not a Codex projection"; skill-manager
"the old overview address opens delivery"; memory "an older build's Codex hook
is moved to SessionStart"; daemon "an idle window left in the daemon config is
ignored and dropped"; secret "bindings in use at upgrade keep working" and "a
signed build moves a file key into its access group"; agent-registry/claude-code
"an entry installed before the config dir was honoured moves to the agent's own
file".
