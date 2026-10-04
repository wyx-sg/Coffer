## Why

When Coffer rewrites an agent's own config file (`~/.codex/config.toml`,
`~/.claude/settings.json`, `~/.claude.json`) it leaves `<file>.bak`, `.bak.1` and
`.bak.2` next to it. Those are clutter inside the agent's directory, they are
swept up by backups and dotfile repositories the user keeps of that directory, and
nothing ever cleans them. Coffer already owns a machine-local, never-synced home
(`~/.coffer`) with a retention framework; backups belong there.

## What Changes

- Every write or delete that used to make a sidecar `.bak` now copies the prior
  content to `~/.coffer/config-backups/<file>-<hash>/<UTC time>.<ext>` before the
  atomic replace. Nothing is written next to the agent's file any more.
- A new `config_backups` retention policy (30 days by default, Keep forever or
  any number of days) deletes old backups, always keeping the newest backup of
  each file. It has a row in Settings > Data > History, is swept by Clear expired
  data now, and is counted in History's size.
- The Review changes dialog and the confirmation dialogs say a backup copy is kept
  in Coffer's folder instead of a `.bak`.
- Existing `.bak`, `.bak.1` and `.bak.2` files already beside agent configs are
  left alone.

## Impact

Specs: agent-registry (and its claude-code and codex children), provider-switching,
resource-framework, daemon, web-ui. Code: `config_file_store`, retention wiring,
storage usage, Settings > Data. Docs: filesystem reference, agents and web-ui
guides, ADR writing-agent-native-config-safely, en and zh.
