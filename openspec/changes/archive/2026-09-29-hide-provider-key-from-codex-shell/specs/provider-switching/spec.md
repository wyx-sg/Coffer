## MODIFIED Requirements

### Requirement: Project into Codex config without clobbering it
The system MUST project into `~/.codex/config.toml` via `tomlkit` (comment- and order-preserving),
merging only the managed keys and preserving everything else; a file that does not exist is created
with only the managed keys. The key reaches Codex through `env_key = "COFFER_PROVIDER_KEY"` in the
`[model_providers.coffer]` table: Coffer materialises it into the environment of any Codex process it
spawns itself, and a Codex the user starts in their own shell needs the variable exported there,
since Codex offers no helper-command seam. Codex's variable is filled from the connection active for
Codex. Codex passes its whole environment to the shell commands the agent runs unless told otherwise
(its built-in filter of names containing `KEY`, `SECRET` or `TOKEN` is off by default), so the
projection MUST also add `COFFER_PROVIDER_KEY` to `shell_environment_policy.exclude`, keeping the
user's own entries and other policy keys; de-projection MUST remove only that entry, and the table
when nothing else is left in it.

`wire_api = "responses"` is the only accepted value, enforced in `AgentConfig`, so anything else is a
422 at the moment it is set: Codex refuses to load a `config.toml` carrying `wire_api = "chat"`, and
rewriting the value at projection time would leave the stored value, and every `AgentOut`, saying
something other than what Coffer projects.

When the connection curates `text` models the system MUST also write the Coffer-owned model catalogue
next to `config.toml` and point `model_catalog_json` at it, writing the file before the pointer and
dropping the pointer before the file; it MUST drop that pointer only when it names the Coffer-owned
filename. That key replaces Codex's built-in model list, which is what is wanted — the built-in names
are not served by the endpoint the agent now calls. De-projection drops the pointer and retires the
file, so Codex's own models come back; an uncurated connection writes no catalogue. The file is a
wire contract with another program: every field Codex's parser requires MUST be emitted, because a
malformed catalogue does not fail loudly — Codex warns and falls back to its built-in list. Values
Coffer cannot derive for a third-party endpoint take the least committal value, and
`base_instructions` is written empty, so Codex sends no `instructions` field: Coffer does not author
another product's system prompt. Claude Code has no equivalent seam (`additionalModelOptionsCache` is
Claude Code's own cache and is clobbered), so for `claude_code` the Coffer-side surfaces stay the only
places the model is chosen.

#### Scenario: activate an openai profile writes Codex config
- **GIVEN** a Codex agent is registered and a connection reaching it exists,
- **WHEN** the user activates the connection,
- **THEN** `~/.codex/config.toml` contains `model` (from the agent's binding), `model_provider = "coffer"`, and a `[model_providers.coffer]` table with `base_url`, `wire_api = "responses"` and `env_key = "COFFER_PROVIDER_KEY"`; and the connection's `is_active` becomes `true`.

#### Scenario: the projected key is hidden from the agent's shell commands
- **GIVEN** a Codex agent whose `config.toml` already has `[shell_environment_policy]` with `exclude = ["AWS_*"]`,
- **WHEN** the user activates a connection reaching it, and later switches the agent back to its built-in login,
- **THEN** after activation `exclude` is `["AWS_*", "COFFER_PROVIDER_KEY"]`, so a shell command the agent runs does not see the key,
- **AND** after the switch back `exclude` is `["AWS_*"]` again.

### Requirement: Clear an active flag the agent's config contradicts at boot
At boot, for each agent type with an active connection reaching it, the system MUST check that the
agent's native config actually carries the projection and MUST clear `is_active` when it does not,
so every surface then says the agent is on its built-in login. For Codex, the
`shell_environment_policy.exclude` entry alone does not count as carrying the projection: it selects no
provider. It MUST NOT write the projection back,
because a flag left from an earlier session is no warrant to re-route a user's agent through a
gateway they are not currently using; the opposite drift — Coffer's keys present while the registry
says inactive — MUST be reported rather than removed. `is_active` is not redundant with `enabled`:
`enabled` is the user's switch on the resource, while `is_active` records that this is the connection
currently written into the agents it reaches — a claim about a file on disk that the agent's own CLI,
other tooling, the user and a restore from backup all rewrite.

#### Scenario: boot clears an active flag the agent's config does not carry
- **GIVEN** an active connection reaching a registered Claude Code agent whose `settings.json` carries none of Coffer's keys
- **WHEN** the boot self-check runs
- **THEN** the connection's `is_active` is cleared
- **AND** the agent's `settings.json` is left exactly as it was, with no projection written back

#### Scenario: a leftover shell exclude entry is not a Codex projection
- **GIVEN** an active connection reaching a registered Codex agent whose `config.toml` holds only `[shell_environment_policy]` with `exclude = ["COFFER_PROVIDER_KEY"]`
- **WHEN** the boot self-check runs
- **THEN** the connection's `is_active` is cleared
