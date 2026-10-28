## Why

`/start` was a hidden alias of `/help` (what Telegram's start button sends). The
owner wants the command set to carry no aliases.

## What Changes

- `HIDDEN_ALIASES` is removed: `/start` is no longer a command, so a bare
  `/start` is an ordinary message for the agent. `/start <CODE>` still claims a
  pairing code (handled before commands, unchanged).
- The main spec (`skip_specs`) and docs no longer mention the alias.

## Impact

- Code: `domain/channel/commands.py`. Tests: command roster, status and help.
- Spec: channels, channels/telegram. Docs: channel-commands, channels-telegram,
  architecture/chat (en + zh).
