## ADDED Requirements

### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` (and `coffer provider builtin <agent_type>`) MUST
remove Coffer's managed keys from every enabled agent of that type and clear the flag of the
connection active for it, idempotently — succeeding when nothing was active — and MUST revert a
connection that reaches several agent types as a unit, because the single `is_active` flag is
all-or-nothing. The route and the command take an agent type; a wire is not accepted, because a
connection reaches agents through its scope and no protocol names an agent.

#### Scenario: switch an agent back to its built-in login
- **GIVEN** a connection is active and projected into Claude Code,
- **WHEN** the user switches Claude Code back to built-in (`POST /providers/use-builtin/claude_code`, or `coffer provider builtin claude_code`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the connection is no longer active; the operation is idempotent (a no-op when nothing is active). A connection is an optional override.

#### Scenario: a wire no longer names an agent to revert
- **GIVEN** the daemon is running
- **WHEN** the user asks to revert `anthropic`, or a type that is not an agent type
- **THEN** the request is refused as `unprocessable_entity` (422) and nothing is written

## MODIFIED Requirements

### Requirement: Validate connection config against the provider schema
The system MUST validate a connection's config against a kind-specific schema over
`{protocol, base_url, credential_ref, models, is_active, internal_default, transcribe_default}`,
rejecting any other key. The config MUST NOT carry a model the connection runs (no `model`, no
`fast_model`), nor the agents it reaches — reach is the resource row's per-agent `scope` — nor a
manually chosen wire format or a `wire_api`: the Codex chat/responses choice belongs to the Codex
binding.

`protocol` says what the endpoint speaks: `anthropic`, `openai`, `ollama` or `unknown`, where
`unknown` means a probe was inconclusive. It drives model introspection and whether a key is
required; it does not choose the agent a connection is written into, but a keyless (`ollama`)
connection reaches no agent whatever its scope says — which is why the wire cannot move under a live
connection (see "Refuse to move the wire of a live connection"). No wire names an agent: each agent
declares the wire protocols its native config speaks, possibly none (see "Keep projection transforms
pure").

#### Scenario: reject a profile with an unknown wire format
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create a connection with `protocol="grpc"`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row is created.

### Requirement: Keep projection transforms pure
Domain projection logic MUST be pure (no I/O). Each agent that can be put on a connection has a
provider entry in its projection facet ([Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md)):
it names the allowlisted file it lands in and the wire protocols the agent's native config speaks
(possibly none), and composes the pure `apply_*` / `remove_*` transforms (`apply_anthropic_settings`,
`apply_codex_provider` and their inverses) into a plan — the main file's new TEXT, the files written
before it and the files removed after it — plus the check whether Coffer's keys are present.
`ProviderProjector` performs the plan: it reads and writes the files, refuses a stale write, and
writes a side file (the Codex model catalogue) before the pointer to it and removes it after the
pointer is gone. The writer is the agent's facet, never chosen by a protocol.

#### Scenario: projection transforms touch no file
- **GIVEN** existing native-config text for Claude Code and for Codex, and file access that fails if attempted
- **WHEN** the anthropic and Codex apply and remove transforms run over that text
- **THEN** each returns new native-config text carrying (or no longer carrying) the managed keys
- **AND** no file is opened, read or written while they run

### Requirement: Audit every provider switch
The system MUST emit an audit event with value `"provider_switched"` for every switch, with details
`{from, to, protocol, agents}` for an activation and `{from, to: null, agent_type, agents}` for a
revert to the built-in login.

#### Scenario: a provider switch is recorded in the audit log
- **GIVEN** a connection is activated,
- **WHEN** the user queries the audit log,
- **THEN** a `provider_switched` entry appears with details `{from, to, protocol, agents}`, a timestamp, and an actor.

### Requirement: Resolve a key for exactly one connection
`coffer provider key --connection-uid <uid>` / `GET /api/v1/providers/{uid}/key` MUST resolve exactly
that connection's credential ref, decrypt via `EncryptedCredentialStore.get(ref)`, and print it to
stdout or return it without logging the value. Keys resolve per CONNECTION, so routing a connection
to the other wire's agent can never resolve a different connection's key; a disabled connection, or
one scoped to no agent, resolves none — by uid as well as by wire, because the uid form is the one a
helper line already written into Claude Code's `settings.json` keeps calling after the user switches
the connection off. Resolving none is `not_found` (404, `NO_ACTIVE_PROVIDER`) on the route, and a
non-zero exit with a message on `stderr` from the CLI; the secret appears in neither. This is the one CLI command that takes a uid instead of a
name: its caller is the `apiKeyHelper` line Coffer writes into another tool's config file, so it MUST
keep resolving to the same connection after a rename. The wire-keyed form (`--wire <wire>` /
`GET /api/v1/providers/active-key/{wire}`) MUST remain for back-compat with `settings.json` files
written before, resolving through the agents whose native config declares that wire: the first such
agent type, in agent-type order, with an active connection answers.

#### Scenario: resolve the active provider key for the apiKeyHelper
- **GIVEN** a connection is active with a known secret stored in the vault,
- **WHEN** its key is resolved — `coffer provider key --connection-uid <uid>`, or the legacy `--wire anthropic` form,
- **THEN** the raw key is printed to stdout and the vault key is NOT logged.
#### Scenario: per-agent key routing follows the connection's scope
- **GIVEN** two activated connections told apart only by their scope — one scoped to `claude_code`, one to `codex`,
- **WHEN** each agent's key is resolved,
- **THEN** each resolves its own connection's key; disabling a connection, or scoping it to no agent, makes it resolve none.
#### Scenario: an agent bound to a renamed connection still resolves its key
- **GIVEN** a Claude Code agent running on connection `acme`,
- **WHEN** `acme` is renamed,
- **THEN** `GET /api/v1/providers/<uid>/key` returns the same secret, the uid the projected `apiKeyHelper` cites still resolves to it, and the connection is still active and still reaches that agent.
#### Scenario: a disabled or unreached connection's uid helper resolves no key
- **GIVEN** a connection activated for Claude Code, which is then disabled, or re-scoped to no agent,
- **WHEN** its key is resolved by uid — `coffer provider key --connection-uid <uid>` or `GET /api/v1/providers/{uid}/key`,
- **THEN** the route answers 404 `NO_ACTIVE_PROVIDER` and the CLI exits non-zero with a message naming the connection,
- **AND** the secret appears in neither.

### Requirement: Refuse to move the wire of a live connection
A connection's `protocol` MUST be correctable — the probe that guessed the wire can be wrong, and
re-entering the key to fix it is a worse answer than editing it. But the wire is not inert, so
changing it MUST be refused with 409 `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while the connection is
active, with a message that names the way out (`coffer provider builtin <agent_type>` for each
agent type the connection reaches). A keyless (`ollama`) connection covers no agent whatever its
scope says (see "Keep ollama connections internal-only").
Moving the wire of a connection that is currently projected would leave the native config Coffer
already wrote standing, with nothing left that would ever take it off. Silently de-projecting instead
MUST NOT be the answer: the developer asked to change a field, not to take their agents off a
gateway. Re-sending the wire the connection already has is not a change, so a client that submits a
whole form is never told its unchanged dropdown is a conflict. The refusal MUST be reachable on every
surface that offers the edit — REST, `coffer provider edit`, and the connection's form.

#### Scenario: correcting a mis-probed wire is refused while the connection is live
- **GIVEN** a connection that is switched on and projected into an agent,
- **WHEN** the user patches its `protocol` to a different wire,
- **THEN** the request is refused `409` `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`, the stored wire is unchanged, and the message names `coffer provider builtin <agent_type>` for the agent types it reaches as the way out
- **AND** re-sending the wire the connection already has is not a change and succeeds, so a client that submits a whole form is never told its unchanged dropdown is a conflict; once the agents are back on their own login, the same patch succeeds (see "Refuse to move the wire of a live connection")

### Requirement: Offer every connection operation on REST, CLI and web
Create, switch, revert-to-built-in, rename and delete MUST be available via (a) the REST API, (b)
`coffer provider list|show|add|edit|rm|enable|disable|scope|switch|builtin|key` with `--json` on
`list` and `show` — the lifecycle verbs being the ones every kind's group offers, and rename being
`coffer provider edit <name> --name <new>` (see "Rename a connection without moving anything
else") — and (c) the web surfaces — the Model providers library for create and delete, the Agent
detail page for the switch, the connection's own page for the rename. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `protocol`, `models`,
`secret_value`, `description`), over the CLI
(`coffer provider edit <name> [--name <new>] [--title <text>] [--description <text>] [--protocol <wire>] [--base-url <url>] [--secret <value>]`)
and from its detail page, including correcting the wire. `coffer provider add <name> --protocol <p>
--base-url <url> [--secret <value> | --credential-ref <ref>]` takes no model. Reverting is
`coffer provider builtin <agent_type>`: a surface that can put an agent onto a Coffer connection and
not take it off again is half an operation. Which connection the internal engine and speech-to-text
run on is set through `coffer config` (see "Set the internal-engine default" and "Keep an
independent speech-to-text default"), not through a `provider` subcommand.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's RESOURCES group; the old
  `/settings/models`, `/settings/providers` and `/settings/llm-connections` routes redirect there) is
  the connection library: a table of name / vendor / base URL / reach, an Add action and Delete per
  row. It has no per-row switch, because activation is per agent. A row MUST say what Coffer ITSELF
  uses the connection for: the `internal_default` connection carries a "Coffer · background model"
  badge and the `transcribe_default` connection a "Coffer · speech to text" badge, each with a hint
  naming where it is changed, and the connection's detail header repeats them. The labels lead with
  Coffer because a bare "Speech to text" reads as a capability of the provider rather than a job
  Coffer gives it; the "Active" badge is a different fact — an agent is switched to the connection —
  and its hint says so. The
  vendor column and its filter are derived from `base_url` by matching the preset list (an unmatched
  endpoint reads as Custom); the name column keeps the user's own name, and the row links to the
  detail page by `uid`.
- The add-connection dialog asks for the protocol rather than detecting it: it offers provider
  presets (OpenAI / Anthropic / Google Gemini / DeepSeek / OpenRouter / Ollama) that fill in the
  endpoint and protocol, plus Custom, which reveals a manual protocol selector; the CLI takes
  `--protocol`. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail page splits into Overview and Models tabs. Its header carries the shared
  scope control — the single place the connection's reach and its enabled state are both shown and
  changed.
- Per-agent connection and model selection lives on the agent detail page's Overview tab, filtered to
  the connections that reach that agent and narrowed by `enabled`. Picking a connection or a model
  there is a DRAFT: it activates nothing and PATCHes nothing. Picking a non-built-in connection
  introspects its endpoint and stages a default model — Claude Code's primary and fast slots and
  Codex's single slot all default to the first model returned. A custom connection MUST pass
  `POST /api/v1/models/test-connection` with the staged model before it can be confirmed; confirm
  stays disabled until the test for the CURRENT draft passes, and changing the connection or the
  model resets the result. Confirming PATCHes the per-agent binding and then activates the
  connection — the only step that writes native config. Switching back to the built-in login needs
  no test.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `credential_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the command line covers create, list, switch and revert
- **GIVEN** the daemon is running,
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch` and `coffer provider builtin <agent_type>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the connection is no longer active for that agent type, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the Agent Overview tab (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the internal-engine default, connection B is the speech-to-text default, and connection C carries neither flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · background model" badge, B's row the "Coffer · speech to text" badge, and C's row neither (TypeScript acceptance test)

## REMOVED Requirements

### Requirement: Revert an agent to its built-in login
**Reason**: The revert was addressed by wire, which assumed one wire stands for exactly one agent. It is now addressed by agent type.
**Migration**: Replaced by "Revert an agent type to its built-in login": call `POST /api/v1/providers/use-builtin/{agent_type}` and `coffer provider builtin <agent_type>` (`claude_code` for what `anthropic` reverted, `codex` for what `openai` reverted).
