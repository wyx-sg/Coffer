## MODIFIED Requirements

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
`coffer provider builtin <wire>`: a surface that can put an agent onto a Coffer connection and
not take it off again is half an operation. Which connection the internal engine and speech-to-text
run on is set through `coffer config` (see "Set the internal-engine default" and "Keep an
independent speech-to-text default"), not through a `provider` subcommand.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's AGENTS group, beside the agents whose models it serves; the old
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
- Per-agent connection and model selection lives on the agent detail page's Model tab, filtered to
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
- **WHEN** the user runs `coffer provider add`, `coffer provider list --json`, `coffer provider switch` and `coffer provider builtin <wire>` from the CLI,
- **THEN** each operation succeeds with the same effect as the HTTP API and `list --json` returns machine-readable output,
- **AND** after the revert the connection is no longer active for its wire, so a terminal-only user can undo the switch they made.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections whose reach differs,
- **WHEN** the page renders,
- **THEN** it lists both connections with their endpoints, marks the active one, and shows each connection's reach in the Reach column's own control — not as a second column repeating it in words — with NO per-row "Switch" action, because activation is per-agent on the agent's Model tab (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the internal-engine default, connection B is the speech-to-text default, and connection C carries neither flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · background model" badge, B's row the "Coffer · speech to text" badge, and C's row neither (TypeScript acceptance test)
