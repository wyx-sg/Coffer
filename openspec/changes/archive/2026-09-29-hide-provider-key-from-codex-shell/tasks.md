No `design.md`: `exclude` is the narrowest of Codex's policy settings. `ignore_default_excludes = false` or `inherit = "core"` would also hide the key, but would change what every other variable the user's shell commands see.

## 1. Projection

- [x] 1.1 `apply_codex_provider` adds `COFFER_PROVIDER_KEY` to `shell_environment_policy.exclude`, once, keeping the user's entries
- [x] 1.2 `remove_codex_provider` removes that entry, and the list and table when empty
- [x] 1.3 The boot self-check ignores `shell_environment_policy` when deciding whether Codex carries the projection

## 2. Tests

- [x] 2.1 Projection: the entry is written, merged with the user's policy without duplication, and removed alone
- [x] 2.2 Boot check: a config holding only the exclude entry is not a projection
- [x] 2.3 Manual check against `codex-cli 0.155.1` (`codex sandbox -- env`, dummy key, isolated `CODEX_HOME`): hidden with the projected config, visible again after de-projection

## 3. Docs

- [x] 3.1 Providers guide, configuration reference, ADR `provider-keys-never-land-in-native-config`
