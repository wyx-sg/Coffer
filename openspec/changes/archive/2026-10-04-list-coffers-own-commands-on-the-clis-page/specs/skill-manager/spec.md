## ADDED Requirements

### Requirement: List the commands Coffer itself runs
Beside the commands skills declare, the stdio MCP launchers and the tools added
by hand, the system MUST list every command Coffer runs itself as a required
command — `git`, titled Git, which keeps the vault's history and syncs it —
with no minimum and no login check, whether or not anything else needs it. Such
a command is checked, cached and handed off like every required command and is
one entry with any skill, server or hand-added declaration of the same name
(the hand-added title taking precedence, then Coffer's). Each command MUST carry
`needed_by_coffer`, the uses Coffer runs it for (`vault_history`, `sync`), empty
when Coffer does not run it; `coffer cli list` names those uses, and the
hand-off prompt for a missing or outdated one says what Coffer itself uses it
for. A command only Coffer needs MUST NOT raise a `cli_*` attention item: the
feature that needs it reports its own (sync's `sync_git_missing`).

#### Scenario: git is listed as needed by Coffer itself
- **GIVEN** no skill, MCP server or hand-added tool requiring `git`, and no `git` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/git`
- **THEN** it is `missing`, titled Git, with `needed_by_coffer` `vault_history` and `sync` and no skills or servers, and its hand-off prompt says Coffer itself uses it to keep the vault's history and to sync the vault
- **AND** the attention list carries no `cli` item for it, and once `git` is installed a check reports it `ready` with no prompt
