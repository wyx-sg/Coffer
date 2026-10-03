## Context

The CLI mirrors the web UI because "Reach every management operation from both
REST and the CLI" made every management route owe a command. An audit of all
187 commands (route each calls, whether the web UI calls that route, which
programs and prompts invoke the command) found two commands run by programs,
nine needed when the daemon is down, a handful named by Coffer's own hand-off
prompts, and one whose job the web UI does not do. This change lands after
`make-knowledge-and-memory-files-only`, which already removed the `knowledge`
and `memory` groups (except the hidden hook entry point) and the `path
knowledge|memory` targets.

## Goals / Non-Goals

**Goals:** a CLI whose every command has a recorded reason; one test that keeps
it that way; no prompt or message pointing at a command that is gone.

**Non-Goals:** removing REST routes (the web UI calls them); adding web UI for
the few operations that lose their only surface (listed below, accepted).

## Decisions

### 1. Four reasons, recorded next to each command

| Command | Reason | Why |
| --- | --- | --- |
| `memory hook` (hidden) | program | the installed memory hook runs it |
| `proxy token` (hidden) | program | an agent's key helper runs it |
| `daemon start`, `stop`, `restart`, `status` | offline | the daemon may be down; the desktop shell, the offline banner and the upgrade hand-off name them |
| `migrate` | offline | runs with the daemon stopped |
| `path logs` | offline | the log files are what is left to read when the daemon will not start |
| `config list`, `get`, `set`, `unset` | offline | only the keys read before the daemon binds (its port), which must be changeable when it cannot start |
| `run` | hand-off | an agent runs a command with secrets set only in its environment |
| `secret list`, `secret set` | hand-off | an agent names a secret for `run`, and stores one read from stdin without the value entering a chat |
| `log audit`, `log mcp`, `log daemon` | hand-off | troubleshooting hand-offs read records that are not files |
| `mcp test` | hand-off | the MCP install hand-off verifies the server answers |
| `vault problems` | no-ui | lists hand edits the vault refused; no page shows them, and editing files directly is now the main way to change knowledge |

The list lives in one module in the CLI package; a test walks the live command
tree and asserts it equals the list, in both directions, and that every row
names one of the four reasons. `--version` and `--verbose` stay as root
options.

### 2. Everything else is removed outright

No aliases and no "moved to" stubs: the 1.0 rearchitecture keeps no backward
compatibility. `scripts/check_removed_commands.py` gains every removed
spelling with where the operation now lives (a web UI page, or a kept
command), so docs and prompts that still name one fail `make lint`.

Accepted losses — operations whose only surface was the CLI:

- `drift list` / `drift repair`: the reconciler repairs drift on its own every
  minute; what needs a person reaches the attention list.
- `usage requests`: the Usage tab shows totals and exports CSV, not the
  per-request list.
- `vault show`: the web UI shows a version's diff, not its full text.
- `scan`'s "installed but not registered" agent list.

### 3. Prompts and messages follow

Every hand-off prompt, error hint and piece of web UI copy that named a removed
command is rewritten to the web UI step or to a kept command (the audit's file
list is the checklist). `coffer config set feature.<key> on` hints become
"switch it on in Settings › General"; `coffer provider builtin` becomes the
Change model dialog; `coffer agent connect` becomes the agent's Connect button;
`coffer skill list|show` in the skill drift hand-off becomes reading the skill
master folder the prompt names.

### 4. `coffer config` narrows to pre-bind keys

The key registry keeps only the keys stored in the daemon's own settings file
(read before it binds). Every other key is a Settings page control; the
registry rows for them, and their tests, go.

## Risks / Trade-offs

- [A person who scripted a removed command] → the removed-commands list says
  where it lives now; the 1.0 line accepts the break.
- [An agent troubleshooting without the CLI] → the hand-off commands it needs
  stay; everything else is files or a prompt to the person.
- [Spec scenarios that exercised behaviour through the CLI lose coverage] →
  each is rewritten to REST or the web UI, and its test follows.

## Migration Plan

Nothing on disk changes. Installed hooks and key helpers call commands that
stay.

## Open Questions

None.
