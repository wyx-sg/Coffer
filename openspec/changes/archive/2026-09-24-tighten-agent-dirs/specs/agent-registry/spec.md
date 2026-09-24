## MODIFIED Requirements

### Requirement: Allow one agent per name and per config directory
The system MUST reject registration that would create a duplicate agent name (409 `conflict`, as for any kind — the label is unique within its kind even though it is not the identity), and MUST reject registering more than one agent for the same config directory. The check compares resolved config directories — a registration without a `config_dir` resolves to its type's standard location — and runs on every move of an agent's directory too. A second agent for a directory already registered is rejected with `conflict` (409) and nothing is persisted. Two agents of the same type on different directories are allowed; which of them answers for the type is "Serve each agent type's model catalogue"'s rule.

#### Scenario: reject duplicate agent name
- **GIVEN** an agent named `codex-work` exists
- **WHEN** the user attempts to register another agent with the same name
- **THEN** registration is rejected with a clear error

#### Scenario: reject a second agent for an already-registered config dir
- **GIVEN** a `codex` agent is already registered (whose config dir is `~/.codex`)
- **WHEN** the user attempts to register another `codex` agent whose config dir resolves to the same directory, even under a different name
- **THEN** registration is rejected with a clear error and nothing is persisted — only one agent may exist per config directory

### Requirement: Serve each agent type's model catalogue
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless an active connection for that agent curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404. The catalogue reads the native config of the one agent that answers for the type: the first enabled agent of that type in name order — the order the registry lists agents in — which is also the agent a chat turn on that type runs against ([chat](../chat/spec.md) "Ship Claude Code and Codex subprocess providers"). Two agents of one type can be registered when their config directories differ ("Allow one agent per name and per config directory"); their names alone decide which answers, so renaming one can change it.

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404

#### Scenario: two agents of one type — the one first by name answers
- **GIVEN** two enabled `claude_code` agents with different config directories, `zeta-work` registered before `alpha-home`
- **WHEN** the agent that answers for `claude_code` is looked up
- **THEN** it is `alpha-home`, whichever was registered first
- **AND** after `zeta-work` is renamed to `aardvark-work` the lookup answers with it instead
