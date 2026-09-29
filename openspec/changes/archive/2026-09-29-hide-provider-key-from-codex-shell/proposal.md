## Why

Codex reads the projected provider's key from `COFFER_PROVIDER_KEY`, and every Codex process Coffer spawns gets that variable in its environment. Codex's default `shell_environment_policy` (`inherit = "all"`, `ignore_default_excludes = true`) passes the whole environment to the shell commands the agent runs, so `env` or `printenv` in a turn prints the plaintext key into the tool output and the transcript. Checked against `codex-cli 0.155.1` with a dummy key and an isolated `CODEX_HOME`: `codex sandbox -- env` shows the variable by default and hides it once `shell_environment_policy.exclude` names it.

## What Changes

- The Codex projection adds `COFFER_PROVIDER_KEY` to `shell_environment_policy.exclude` in `config.toml`, keeping the user's own entries and other policy keys. De-projection removes only that entry, and the table when it is left empty.
- The boot self-check leaves `shell_environment_policy` out of its "does the config carry the projection" comparison, so a leftover exclude entry alone does not keep a stale `is_active` flag.
- Docs: the providers guide's Codex example, the configuration reference and ADR `provider-keys-never-land-in-native-config` describe the exclude entry.

## Capabilities

### New Capabilities

### Modified Capabilities
- `provider-switching`: "Project into Codex config without clobbering it" writes and removes the exclude entry; "Clear an active flag the agent's config contradicts at boot" does not count that entry as a projection.

## Impact

- Backend: `domain/provider/codex_shell_env.py` (new: the exclude entry's add and remove), `domain/provider/projection.py` (`apply_codex_provider`, `remove_codex_provider`), `application/provider/boot_reconcile.py`.
- Tests: `tests/unit/domain/provider/test_projection.py`, `tests/unit/application/provider/test_projection_boot_heal.py`.
- Docs: `docs-site/guides/providers.md`, `docs-site/reference/configuration.md`, `docs/decisions/provider-keys-never-land-in-native-config.md`.
