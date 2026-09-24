## MODIFIED Requirements

### Requirement: Locate Codex at ~/.codex
The `codex` type's standard config directory MUST be `~/.codex/`, which is the value `config_dir` defaults to under [agent-registry](../spec.md) "Validate agent configuration against the agent schema". The presence of that directory MUST be the install marker [agent-registry](../spec.md) "Discover installed agents as candidates without registering them"'s discovery scans for, and [agent-registry](../spec.md) "Allow one agent per name and per config directory"'s one-agent-per-config-directory rule follows from it: Codex is registrable once unless the user overrides the path. An overridden `config_dir` is the directory Codex is run against through its `CODEX_HOME` environment variable — the only way Codex reads a home other than `~/.codex`, and the root of its `config.toml`, `auth.json`, sessions and memories. Every Codex process Coffer itself starts for such an agent — a chat or channel turn, per [chat](../../chat/spec.md) "Ship Claude Code and Codex subprocess providers", and the `model/list` probe of "Read Codex models from model/list and config.toml" — MUST carry `CODEX_HOME=<config_dir>`; for the default `~/.codex` the variable is left unset.

#### Scenario: discover Codex by its config directory
- **GIVEN** a home directory containing `~/.codex/` and no agent registered
- **WHEN** the user runs discovery
- **THEN** a `codex` candidate is reported whose `config_dir` is `~/.codex`
- **AND** a `codex` agent registered without a `config_dir` resolves to `~/.codex`

### Requirement: Read Codex models from model/list and config.toml
The catalogue sources of [agent-registry](../spec.md) "Read the model catalogue back from the installed agent" for this type MUST be Codex's own `model/list` app-server RPC, plus the models configured in `config.toml` as the native-config contribution of [agent-registry](../spec.md) "Contribute models from the type's native config read-only". The RPC is reachable only when the CLI is installed and authenticated, so it is one degradable source, never a precondition of the response: an unauthenticated or wedged agent answers nothing over RPC and costs exactly those entries. The RPC is asked of the Codex whose home is the agent's config directory ("Locate Codex at ~/.codex"), and its answer is held per config directory, never shared between two: two homes can be two logins.

#### Scenario: fall back to configured models when model/list answers nothing
- **GIVEN** a `codex` config directory whose `config.toml` names a model, and a Codex CLI whose `model/list` RPC cannot be reached
- **WHEN** the Codex catalogue sources are read in order
- **THEN** the configured model is offered
- **AND** no RPC entry appears and the read does not fail

#### Scenario: ask model/list of the agent's own Codex home
- **GIVEN** a `codex` agent registered with a `config_dir` other than `~/.codex`
- **WHEN** the Codex catalogue sources are read for it
- **THEN** the `model/list` app-server is started with `CODEX_HOME` set to that `config_dir`, the rest of the daemon's environment intact
- **AND** a probe for the default `~/.codex` starts with the environment untouched, and neither directory's answer is served for the other
