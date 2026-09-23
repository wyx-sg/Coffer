## MODIFIED Requirements

### Requirement: Support exactly the Claude Code and Codex agent types
The system MUST support the agent types `claude_code` and `codex`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). The rejection carries the generic request-validation message and never echoes the submitted value back. Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`), so adding a type is one enum value, one descriptor record and one child spec (plus, where the product's wire protocol is new, one chat-provider adapter). Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

What a facet looks like for one type is that type's child spec. There is no per-facet capability matrix, no per-facet "not supported" state on the agent surface and no capability booleans on the wire; a facet a type could not support would be a reason not to add that type. The `PluginCapability` flags of "Toggle a plugin through the documented location only" and "Uninstall a plugin by the type's own strategy" are the one exception, and they are per-facet *runtime availability* — whether the agent's own uninstall command is on `PATH` — not a per-type support claim. A further product is added only when it is genuinely in use and its facets can be exercised on a real install; `opencode`, `hermes`, `cursor` and `openclaw` were removed for lacking exactly that.

#### Scenario: reject unsupported agent type
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value)
- **THEN** registration is rejected with `unprocessable_entity` (422), and nothing is persisted

### Requirement: Validate the config directory at registration
At registration the system MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value. The privileged locations are `/etc`, `/bin`, `/sbin`, `/usr`, `/var`, `/sys`, `/proc`, `/root`, `/boot`, `/dev`, `/System` and `/Library/Application Support/Apple` on POSIX hosts — matched at a path-component boundary, after resolving symlinks and stripping macOS's `/private` firmlink prefix, with the user temp area under `/var/folders/` carved out as usable — and `C:\Windows`, `C:\Program Files` and `C:\Program Files (x86)` on Windows. A rejected registration leaves no partial state, and no `config_dir` value may permit writing outside the directory itself.

#### Scenario: reject registration with an invalid config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent whose `config_dir` does not exist, is not a directory, or is not writable
- **THEN** registration is rejected with a message naming the path, and nothing is persisted

#### Scenario: reject registration into privileged system path
- **GIVEN** the daemon is running
- **WHEN** the user attempts to register an agent whose `config_dir` resolves under a privileged location (e.g. `/etc`, `/usr`, `/var` outside `/var/folders/`, `/System`, `C:\Windows`, or `C:\Program Files`)
- **THEN** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs

#### Scenario: register an agent with a custom config dir
- **GIVEN** the daemon is running
- **WHEN** the user registers an agent of supported type with an explicit, writable `config_dir`
- **THEN** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `coffer agent list`

### Requirement: Define a curated config-file allowlist per type
Each supported agent type MUST define a curated allowlist of config files in its capability-manifest record, enumerated by that type's child spec, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml` or `markdown`). Each type's human-authored instructions file carries the key `instructions` — those files are instructions a person wrote, distinct from agent-written memory (memory's domain). Config files are not persisted in SQLite — the file on disk is the source of truth.

#### Scenario: key each type's instructions file as instructions
- **GIVEN** the capability manifest for every supported agent type
- **WHEN** the type's config-file allowlist is read
- **THEN** every entry carries a key, a display name, an absolute path and a format among `json`, `toml` and `markdown`
- **AND** exactly one entry per type is keyed `instructions` and has format `markdown`

### Requirement: Validate config-file content before saving it
The system MUST expose a write (save) for the content of any allowlisted config file through the in-app editor, the REST API and the `coffer agent` CLI — one endpoint serving all three. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown` files accept any content.

#### Scenario: reject malformed config-file content
- **GIVEN** a registered agent whose `settings.json` (a `json` file) exists
- **WHEN** the user writes malformed content (e.g. invalid JSON) to that key through the in-app editor, the REST API or the `coffer agent` CLI
- **THEN** Coffer responds `unprocessable_entity` (422), leaves the on-disk file unchanged, writes no `.bak`, and records no write audit entry

### Requirement: Route secret-like environment values to the credential store on adoption
Adoption MUST NOT persist secret values into resource config. When an entry's environment or HTTP headers carry values under secret-like keys (defined below), the adopt request MUST supply a credential mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored as Fernet ciphertext in Coffer's credential store through the daemon (per the credentials invariant); the resource config carries references only. A key is secret-like when its value is non-empty and its name matches `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `API_KEY`/`APIKEY`, `CREDENTIAL` or `AUTHORIZATION`, case-insensitively.

#### Scenario: require a credential mapping for secret-like env values
- **GIVEN** a direct MCP entry whose environment contains a value under a secret-like key (e.g. `API_TOKEN`)
- **WHEN** the user adopts the entry without supplying a credential mapping for that key
- **THEN** the request is rejected with a response listing the unresolved keys; when the mapping is supplied, the secret is stored in the credential store via the daemon and the created resource config carries a reference, never the value

### Requirement: Serve each agent type's model catalogue
`GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per agent type, which models a picker offers for that agent: the agent's own catalogue, read back from the installed agent and never written down in Coffer, unless an active connection for that agent curates a set of ids — then those ids, as [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface" defines. Each entry MUST carry `id` (passed to the agent verbatim), `label`, `description`, the reasoning `efforts` its runtime reports and the `default_effort` it would use, keeping a reported default only when it is one of the offered levels. An unknown `agent_key` MUST be a 404.

#### Scenario: list the models an agent can be put on
- **GIVEN** a registered `codex` agent whose own config names a model
- **WHEN** the user requests `GET /api/v1/agent-providers/codex/models`
- **THEN** the response lists that model with `id`, `label`, `description`, `efforts` and `default_effort`
- **AND** the same request for an unknown agent key answers 404

### Requirement: Keep one source of truth for an agent's models
There MUST be exactly one source of truth. No Coffer surface may keep a model list of its own: the agent's catalogue is the answer of "Serve each agent type's model catalogue", and what a picker is OFFERED — which narrows to an active connection's curated set where there is one — is [provider-switching](../provider-switching/spec.md) "Serve one model list to every surface"'s answer, served over the wire from that one backend rather than reassembled by any client. Nothing in Coffer curates an agent's models; two attempts to have someone curate them, first on the agent and then on the channel, were both removed. The accepted cost is that a model the agent's own catalogue does not name cannot be PICKED from a Coffer surface — it stays typeable wherever the CLI accepts a name. The benefit is that a newly released model reaches every surface with no Coffer release at all.

#### Scenario: offer the agent's whole catalogue with nothing curated on the agent
- **GIVEN** a registered agent whose installed agent reports several models and no active connection curating a set
- **WHEN** the models offered for that agent are read
- **THEN** every model the agent reports is offered, in the order reported
- **AND** the agent resource carries no model list of its own
