## MODIFIED Requirements

### Requirement: Register each connection as a provider resource
The system MUST register each managed connection as a Resource of kind `provider`, identified by the
framework's immutable `uid`
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md));
its `name` is a mutable label, validated by `validate_name` and unique within the kind. The `provider`
kind declares no scope: a connection reaches the agents its addresses serve (see "Derive the agents a
connection serves from its addresses"), and no surface offers it an off switch.

#### Scenario: a connection is a provider resource addressed by its uid
- **GIVEN** a running daemon
- **WHEN** the user creates a connection named `acme` and then tries to create a second connection named `acme`
- **THEN** the first is returned with a minted `uid` distinct from its name, and the framework's resource routes report it at that `uid` as kind `provider` labelled `acme`
- **AND** the second create is refused with 409 `RESOURCE_ALREADY_EXISTS` and no second row exists


### Requirement: Validate connection config against the provider schema
The system MUST validate a connection's config against a kind-specific schema over
`{protocol, base_url, anthropic_base_url, secret_ref, models, transcribe_default, local_runtime}`,
rejecting any other key. The one retired key, `internal_default`, is accepted and ignored
(see "Ignore a stored internal-default flag"). The config MUST NOT carry a model the connection runs (no `model`, no
`fast_model`), nor the agents it reaches — those follow from its addresses — nor a
manually chosen wire format or a `wire_api`: Codex loads only `responses`, so the Codex block writes that
fixed value and nothing stores it.

`protocol` says what the endpoint speaks: `anthropic`, `openai` or `unknown`, where
`unknown` means a probe was inconclusive. A fourth value, `ollama`, is retired: it is never offered and
a stored one is only read (see "Stop offering the ollama protocol"). The protocol drives model
introspection, whether a key is required and, with `anthropic_base_url`, which agents the connection
serves (see "Give a connection an Anthropic address"); the wire cannot move under a live connection (see "Refuse to move the wire of a live connection"). The config carries no flag saying a
connection is switched on: which agent runs on which connection is a field of the agent record (see
"Keep an agent on at most one connection"). No wire names an agent: each agent
declares the wire protocols its native config speaks, possibly none (see "Keep projection transforms
pure").

#### Scenario: reject a profile with an unknown wire format
- **GIVEN** the daemon is running,
- **WHEN** the user attempts to create a connection with `protocol="grpc"`,
- **THEN** the request is rejected with `422 Unprocessable Entity` and no row is created.


### Requirement: Keep an agent on at most one connection
Which connection an agent runs on MUST be one field of the agent record, `AgentConfig.connection_uid`
([agent-registry](../agent-registry/spec.md) "Carry the connection an agent runs on on the agent
record"), so an agent runs on at most one connection by construction: there is no flag on the
connection that could be set on two of them. Switching an agent onto a connection changes that agent's
field and its own native config file and nothing else — another agent of the same type, or one of
another type, that runs on the previous connection stays on it. One pure function,
`connection_for_agent(agent, connections)`, answers which connection an agent is on, and projection,
the proxy's route, the chat model list and the protocol lock all ask it. A
connection SERVES an agent when the agent's `connection_uid` names it, it exists, is enabled, is not a
stored `ollama` connection, and it has an address for the wire the agent speaks (see "Derive the agents
a connection serves from its addresses"); a pointer that names a missing or switched-off connection, or
one with no address for that wire, means the agent is treated as on its built-in login, and the reconciler reports
the keys left in its file rather than silently routing it elsewhere.

#### Scenario: switching one agent onto a connection moves only that agent
- **GIVEN** a Claude Code agent and a Codex agent that both run on connection A, and a connection B that reaches Claude Code
- **WHEN** the user switches the Claude Code agent onto B
- **THEN** the Claude Code agent's `connection_uid` is B's uid and its `settings.json` carries B's projection
- **AND** the Codex agent still runs on A, with its `config.toml` and `connection_uid` untouched


### Requirement: Switch one agent at a time
`POST /api/v1/providers/{uid}/activate` with body `{agent_type}` (the agent's Change model dialog calls it) MUST switch THAT agent onto the
connection. The operation:

1. requires the connection to exist, else 404, and the agent of that type to be registered, else 404;
2. refuses with 409 `PROVIDER_DOES_NOT_REACH_AGENT` when the connection is switched off or has no
   address for the wire the agent speaks (the message says to add an Anthropic address for Claude
   Code), and with 422 `PROVIDER_PROTOCOL_RETIRED` for a stored `ollama` connection;
3. projects the connection into that agent's native config file, recording the file's prior content;
4. sets the agent's `connection_uid` to the connection's uid;
5. emits `provider_switched`;
6. returns `{activated, protocol, agent_type, agent}`.

The projection MUST run before the agent record is written, and a failure at any step MUST put the
file back and leave the record unchanged, so the agent is never left pointed at the proxy with no
connection behind it. The operation writes no other agent's file and no other agent's record.

Reach follows from the connection's addresses (see "Derive the agents a connection serves from its
addresses"); there is no `compatible_agents` field in the config, in `ProviderCreate` or in
`ProviderPatch`, and no scope. A stored `ollama` connection (a retired wire) projects to no agent. The
projection writer MUST be chosen by AGENT type, not by protocol: a connection reaching `claude_code`
writes Claude's `settings.json` in the anthropic shape, pointing at the proxy route whose upstream is
the connection's Anthropic address, and one reaching `codex` writes Codex's `config.toml`. Coffer
translates nothing between protocols.

#### Scenario: a switch whose write fails puts the file back
- **GIVEN** a Codex agent whose `config.toml` the user edits between Coffer's read and its write
- **WHEN** the user switches the agent onto a connection and the write is refused as stale
- **THEN** the switch fails with `config_file_stale`, the user's Codex edit survives, and the agent's `connection_uid` is unchanged

#### Scenario: a connection the agent is not reached by is refused
- **GIVEN** a registered Codex agent and an `anthropic` connection, which has no OpenAI address
- **WHEN** the user switches the Codex agent onto it
- **THEN** the switch is refused with 409 `PROVIDER_DOES_NOT_REACH_AGENT`, no file is written and the agent's `connection_uid` is unchanged

#### Scenario: route an openai-compatible connection to Claude Code with its scope
- **GIVEN** a Claude Code agent is registered and an `openai`-wire connection is created with an Anthropic address,
- **WHEN** the user switches the Claude Code agent onto that connection,
- **THEN** it projects into Claude Code's `settings.json` (the anthropic shape) with `apiKeyHelper = "<absolute path to the coffer CLI> proxy token --agent-uid <agent uid>"`, and the model proxy routes that agent's requests to exactly that connection with that connection's key.


### Requirement: Revert an agent type to its built-in login
`POST /api/v1/providers/use-builtin/{agent_type}` MUST
remove every key Coffer wrote from the agent of that type — for Claude Code `apiKeyHelper`,
`env.ANTHROPIC_BASE_URL`, the top-level `model`, the four
`env.ANTHROPIC_DEFAULT_<TIER>_MODEL` pins, Coffer's `modelPicker`, the local-runtime compatibility
keys and Coffer's `env.NO_PROXY` pair; for Codex the provider table, `model_provider`, `model`, and the catalogue pointer and file — so no
stale pin keeps redirecting a tier after the agent is back on its own login. A `model` the
user has since changed through `/model` no longer equals the agent's binding, is theirs
and is kept. An `effortLevel` or `model_reasoning_effort` that an earlier version wrote carries no mark of its own, so it is the user's and is kept too. Only values Coffer wrote are removed: the `env` keys carry no mark of their own, so they
count as Coffer's only while Coffer's `apiKeyHelper` is in the file ([data-model.md](data-model.md)
"What is Coffer's"); a user's own `ANTHROPIC_BASE_URL` or tier pins beside no Coffer helper are left
untouched and are not reported as drift. It also clears that agent's `connection_uid`, idempotently — succeeding when
the agent was on no connection — and touches only that agent: another agent that runs on the same
connection stays on it. The route takes an agent
type; a wire is not accepted, because no protocol names an agent.

#### Scenario: switch an agent back to its built-in login
- **GIVEN** the Claude Code agent runs on a connection and is projected into it,
- **WHEN** the user switches Claude Code back to built-in (`POST /providers/use-builtin/claude_code`),
- **THEN** Coffer's managed keys are removed from the agent's native config so it falls back to its own login, and the agent's `connection_uid` is empty; the operation is idempotent (a no-op when the agent is on no connection). Another agent running on the same connection is untouched. A connection is an optional override.

#### Scenario: a wire no longer names an agent to revert
- **GIVEN** the daemon is running
- **WHEN** the user asks to revert `anthropic`, or a type that is not an agent type
- **THEN** the request is refused as `unprocessable_entity` (422) and nothing is written

#### Scenario: switching back removes every key Coffer wrote
- **GIVEN** a Claude Code agent on a connection, with Coffer's `apiKeyHelper`, `env.ANTHROPIC_BASE_URL`, `model`, three tier pins and `modelPicker` in `settings.json`, beside a `theme` key of the user's, and a Codex agent on a connection with a curated catalogue

- **WHEN** the user switches both agents back to their built-in login
- **THEN** none of the keys Coffer wrote remain in `settings.json` and `theme` is untouched
- **AND** the Codex `config.toml` holds no `model_provider = "coffer"`, provider table, catalogue pointer Coffer wrote, and the catalogue file is gone

#### Scenario: switching back leaves the user's own gateway settings alone
- **GIVEN** a Claude Code `settings.json` with the user's own `env.ANTHROPIC_BASE_URL`, a tier pin and `theme`, and no Coffer `apiKeyHelper`
- **WHEN** the user switches Claude Code back to built-in, or a reconcile pass with a warrant runs
- **THEN** the file is byte-identical afterwards and attention reports no `projection_unclaimed` drift for it


### Requirement: Offer every connection operation over REST and in the web UI
Create, switch, revert-to-built-in, rename, edit and delete MUST be
available via (a) the REST API and (b) the web surfaces — the Model providers library for create and
delete, the Agent detail page for the switch and the revert, the connection's own page for the
rename and the edit (see "Rename a connection without moving anything else"). A connection has no
scope and no off switch: the agents it serves follow from its addresses. The `coffer provider` and `coffer model` commands call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). The list carries no Active column, and a
connection's lifecycle verbs are the ones every kind's page offers. Editing a connection MUST be
available over REST (`PATCH /api/v1/providers/{uid}`: `base_url`, `anthropic_base_url` (`""`
clears it), `protocol`, `models`, `secret_value`, `description`) and from its detail page, including
correcting the wire. Creating one (`POST /api/v1/providers` with a name, a protocol, a base URL, an
optional Anthropic address and an inline secret, a secret ref or the `local_runtime` detection) takes no model; a local runtime connection is created
without a key (see "Configure a local model connection"). No route returns a provider's key: the
agents reach a connection through the local model proxy, which injects the key itself (see "Reach
API-key and local connections through the local model proxy"). Reverting is
`POST /api/v1/providers/use-builtin/{agent_type}`, offered by the agent's Change model dialog as its
built-in login: a surface that can put an agent onto a Coffer connection and not take it off again is
half an operation. Which connection speech-to-text runs on is chosen in
Settings › General (see "Keep an independent speech-to-text
default"), not on the connection's own page.

The web surfaces:

- **Model providers** (route `/model-providers`, in the sidebar's Agents group, beside the agents whose models it serves) is
  one page under one header — the title, an Experimental tag, a one-line description and the page's one primary button, **Add provider** — over two tabs, **Providers** and **Usage** ("Show metered usage on a Usage tab of Model providers"). Providers is the connection library: a list of connections beside the open one. It has no view of which agent runs on what and no Coffer's model tab, because an agent's connection is shown and changed in that agent's Overview › Model and the speech-to-text connection is chosen in Settings › General. The page opens on the first connection, and with none it is a welcome panel. Each row shows
  the connection's vendor mark, its name, its protocol and what it offers (its curated model count,
  or all models), and the marks of the agents running on it, read from the agents' `connection_uid`; a filter narrows the list over name,
  title, endpoint and description, and the list is sorted by name, with no order heading and no drag handle on a row. It has no per-row switch, because activation is per agent, and no
  per-row delete: it is on the open connection's header. A row MUST say what Coffer
  ITSELF uses the connection for: the `transcribe_default` connection carries a "Coffer · speech to
  text" badge with a hint naming Settings › General as where it is changed, and the connection's Used by repeats
  it. The label leads with Coffer because a bare "Speech to text" reads as a capability of the
  provider rather than a job Coffer gives it; an agent's mark on a row is a different fact — that
  agent is switched to the connection. The vendor mark is derived from `base_url` by matching the
  preset list (an unmatched endpoint gets Coffer's neutral provider glyph); the name is the user's
  own, and the row links to the detail page by `uid`.
- The add-connection dialog asks for the vendor from a grid of equal buttons (see "Offer the
  mainstream vendors as presets"), which fill in the vendor's addresses, in two steps, Endpoint and then
  Models. It asks for addresses, not a protocol (see "Ask for addresses, not a protocol"). A local runtime (Ollama, LM Studio) asks for no key, offers only the wires the detected runtime serves to agents (Anthropic, OpenAI) and,
  until a runtime is detected, does not let the user go on to Models; the connection's Name
  appears once a runtime is chosen. The dialog surfaces test-connection and list-models with an inline, not-yet-saved
  secret.
- The connection detail (`/model-providers/<uid>`, addressed by `uid` because a connection can be renamed) is one column opened beside the list — Used by, Endpoint, Models — and has no tabs. Its header carries a health pill (Reachable, Key rejected or Unreachable, read from a probe that runs when it opens), the agents its addresses serve ("For Claude Code, Codex", or that none can use it), the host and, when the endpoint answered, how long it took, with Test, Edit and a menu holding Delete provider ("Review what deleting a connection changes"). **Used by** is read-only: each agent whose `connection_uid` names the connection (and that the connection still serves),
  with the model it runs, as a link reading "<Agent> › Change model" that opens that agent's page with its Change model dialog already open (`/agents/<type>?change-model=1`); and Speech to text
  when the connection is flagged for it, reading "Settings › General" and opening it. Used by carries no
  switch, activate or revert control, and no row repeats a fault: a connection's fault shows in its header pill and in the section it belongs to (Endpoint for Unreachable or Key rejected, Models for a failed listing).
- Per-agent connection and model selection lives on the agent detail page's **Overview › Model** section and its **Change model** dialog; the agent page has no Model tab. The section reads **Provider**, **Model** and **Route** and carries **Change…**. The dialog is one 480-wide form for both agents ("Review a model change before writing it"), filtered to the connections that serve that agent: **Provider** (the agent's built-in login or a connection), then, for a connection, **Model** and, for Claude Code, **Model per tier** (Opus, Sonnet, Haiku, and Fable only when the connection lists a Fable model; see "Suggest a model for each Claude Code tier"). It carries no
  other model setting — no output-limit, subagent, thinking or fast-mode
  control — because what else a model needs Coffer derives and writes itself. Picking a non-built-in
  connection introspects its endpoint and stages a default model — the first model returned — and
  the tier suggestions for it. Picking things in the form is a DRAFT: it writes nothing, and **Review changes** is enabled only once the draft differs from what is applied, names a model and has passed its connection test ("Review a model change before writing it"). On the built-in login Model is the agent's own model and optional, and no test runs. The agent's Overview reads the connection the agent is on from the agent record's `connection_uid`, not from any flag on a connection.

#### Scenario: update a provider profile
- **GIVEN** a connection exists,
- **WHEN** the user patches `base_url` (no `secret_value`),
- **THEN** only that field is updated, `secret_ref` is unchanged, and `resource_updated` is audited.
#### Scenario: the routes cover create, list, switch and revert
- **GIVEN** the daemon is running,
- **WHEN** a client calls `POST /api/v1/providers`, `GET /api/v1/providers`, `POST /api/v1/providers/{uid}/activate` with an `agent_type` and `POST /api/v1/providers/use-builtin/{agent_type}`,
- **THEN** each operation succeeds and the list answers with the connections as JSON,
- **AND** after the revert the agent's `connection_uid` is empty, so the switch that was made can be undone.
#### Scenario: the connections page lists profiles and their compatible agents
- **GIVEN** the connections page is rendered with two mock connections that serve different agents,
- **WHEN** the page renders,
- **THEN** it lists both connections, marks the one an agent runs on with that agent's mark, and shows the open connection's address and, in its header, the agents it serves, with NO per-row "Switch" action, because activation is per agent in its Change model dialog (TypeScript acceptance test).

#### Scenario: the library names the connections Coffer itself uses
- **GIVEN** connection A is the speech-to-text default, and connection B carries no flag
- **WHEN** the Model providers library is opened
- **THEN** A's row carries the "Coffer · speech to text" badge and B's row carries none (TypeScript acceptance test)

#### Scenario: the provider library has no tabs
- **GIVEN** the Model providers page
- **WHEN** it renders
- **THEN** its only tab strip is the page header's Providers | Usage, and the library itself has no view of which agent runs on which connection and no Coffer's model tab (TypeScript acceptance test)

#### Scenario: a provider's used-by list is read-only
- **GIVEN** a connection that Claude Code runs on (its `connection_uid`) with a chosen model, and that is flagged `transcribe_default`
- **WHEN** its detail page renders
- **THEN** Used by lists Claude Code with its model, as a link "Claude Code › Change model" to `/agents/claude_code?change-model=1`, and Speech to text, opening `/settings/general`
- **AND** Used by carries no switch, activate or revert control (TypeScript acceptance test)

#### Scenario: the Change model dialog shows only provider, model and tiers
- **GIVEN** a Claude Code agent on a non-Claude connection, and a Codex agent on a connection
- **WHEN** each agent's Change model dialog renders
- **THEN** Claude Code's shows Provider, Model and Model per tier, and Codex's shows Provider and Model
- **AND** neither shows an effort, output-limit, subagent, thinking or fast-mode control


### Requirement: Stop offering the ollama protocol
The `ollama` protocol (the Ollama-native API) is retired. Creating a connection with it
(`POST /api/v1/providers`) and moving a connection onto it (`PATCH /api/v1/providers/{uid}` with
`protocol="ollama"` for a connection that does not already hold it) MUST be refused with `422
PROVIDER_PROTOCOL_RETIRED` before anything is stored. The message names the way on: a local Ollama
runtime is added on its Anthropic or OpenAI wire. A stored connection that already holds `ollama`
MUST stay readable and listed, MUST reach no agent, MUST be refused with the
same code when an agent is switched onto it, and MUST remain deletable; its other fields stay
editable, and re-sending its stored protocol is not a move. The add-connection dialog MUST NOT offer
`ollama`: a detected local runtime offers only the wires it serves to agents, and a stored
`ollama` connection still renders on the list and its detail page. The local Ollama runtime itself is
unaffected: it is reached over its Anthropic and OpenAI wires.

#### Scenario: refuse to create a connection on the ollama protocol
- **GIVEN** the daemon is running,
- **WHEN** the user creates a connection with `protocol="ollama"`,
- **THEN** the request is refused `422` `PROVIDER_PROTOCOL_RETIRED` and no connection is stored

#### Scenario: refuse to move a connection onto the ollama protocol
- **GIVEN** a connection on the `anthropic` protocol,
- **WHEN** the user patches its `protocol` to `ollama`,
- **THEN** the request is refused `422` `PROVIDER_PROTOCOL_RETIRED` and the stored protocol is unchanged

#### Scenario: a stored ollama connection stays readable and deletable
- **GIVEN** a stored connection whose protocol is `ollama`,
- **WHEN** the user lists connections, reads it, re-sends its protocol in a patch and deletes it,
- **THEN** it is listed with no reachable agent, the patch succeeds, and the delete removes it

#### Scenario: activating an ollama connection writes no native config
- **GIVEN** a registered Claude Code agent and a stored `ollama` connection
- **WHEN** the user switches the agent onto the connection
- **THEN** the switch is refused with `422 PROVIDER_PROTOCOL_RETIRED`, no native config file is written and the agent's `connection_uid` is unchanged
- **AND** the connection reports no reachable agent


### Requirement: Test a connection on the wire the agent speaks

The connection test behind the Change model dialog and Overview › Model › Test MUST speak the wire
the agent will use, not the connection's own protocol: Claude Code is tested on the Anthropic wire
at the connection's Anthropic address (its base URL when it has none), any other agent on the
connection's protocol at its base URL. An endpoint that serves no Messages API there then fails the
test before the switch can be reviewed, instead of every Claude Code turn failing after it.

#### Scenario: Claude Code tests an OpenAI-protocol connection on the Anthropic wire
- **GIVEN** a connection with protocol `openai` that reaches Claude Code
- **WHEN** the user picks it and a model in Claude Code's Change model dialog
- **THEN** the test is sent with protocol `anthropic`, the connection's Anthropic address and its secret ref


## REMOVED Requirements

### Requirement: Offer a vendor's Anthropic endpoint as its own connection
**Reason**: The user chose one connection with two addresses over a connection per wire.
**Migration**: A vendor's Anthropic address is the connection's `anthropic_base_url` (see "Give a connection an Anthropic address"); existing DeepSeek connections get it at startup.

## ADDED Requirements

### Requirement: Give a connection an Anthropic address

A remote `openai` connection MAY carry `anthropic_base_url`, the address where the same account serves
the Anthropic Messages wire when that is not at `base_url` (DeepSeek: `https://api.deepseek.com` and
`https://api.deepseek.com/anthropic`), so one connection serves Claude Code and Codex (ADR
one-connection-serves-both-wires). Any other connection MUST be refused one (422). The model proxy
MUST send the Anthropic wire to `anthropic_base_url` when set and every other wire to `base_url`. The
key's approved destination names both addresses, so adding or moving the Anthropic address waits for
approval like a new base URL; the same address as `base_url` sends the key nowhere new. A stored key
may be tried against either address of the saved connection that holds it. A blank value is no
address, and the read carries `anthropic_base_url` (or `null`).

#### Scenario: the Anthropic wire goes to the Anthropic address
- **GIVEN** a connection with base URL `https://api.deepseek.com` and Anthropic address `https://api.deepseek.com/anthropic`
- **WHEN** Claude Code and Codex both run on it
- **THEN** the proxy relays Claude Code's requests to `https://api.deepseek.com/anthropic` and Codex's to `https://api.deepseek.com`

#### Scenario: adding an Anthropic address waits for the key's approval
- **GIVEN** a connection whose key is approved for its base URL
- **WHEN** an Anthropic address at another root is added
- **THEN** the key waits for approval for the new destination before it is sent there

### Requirement: Ask for addresses, not a protocol

The Add and Edit dialogs MUST ask a remote connection for its addresses rather than its protocol: an
**OpenAI-compatible address**, which Codex uses, and an **Anthropic-compatible address**, which
Claude Code uses, each saying so. At least one is required, and each one typed must be a full URL.
The stored shape follows: an OpenAI address makes the connection `openai` with the Anthropic address
as its second; an Anthropic address alone makes it `anthropic`. A vendor preset shows the addresses
the vendor has, filled in; Custom shows both, empty, with a hint to fill what the gateway serves (the
same address twice for one that serves both at one address). Edit shows both for a remote connection
and the one address of a local runtime, and sends the addresses only when one moved. Test probes the
OpenAI address when there is one, else the Anthropic address.

#### Scenario: DeepSeek fills both of its addresses in one connection
- **GIVEN** the Add dialog
- **WHEN** the user picks DeepSeek
- **THEN** the OpenAI-compatible address is `https://api.deepseek.com`, the Anthropic-compatible address is `https://api.deepseek.com/anthropic`, and no protocol is asked for (TypeScript acceptance test)

#### Scenario: Custom asks for the addresses the gateway serves
- **GIVEN** the Add dialog
- **WHEN** the user picks Custom
- **THEN** both address fields show, empty (TypeScript acceptance test)

#### Scenario: a vendor shows only the addresses it has
- **GIVEN** the Add dialog
- **WHEN** the user picks OpenAI
- **THEN** only the OpenAI-compatible address shows, filled with `https://api.openai.com/v1` (TypeScript acceptance test)

### Requirement: Derive the agents a connection serves from its addresses

A connection MUST serve exactly the agents whose wire it has an address for (ADR
provider-reach-is-what-its-addresses-serve): Claude Code needs an Anthropic address (an `anthropic`
connection's base URL, or an `openai` connection's `anthropic_base_url`), Codex an OpenAI one. A
local runtime serves the wires detection found; an `unknown` connection serves both, since the probe
could not tell and the switch test decides; a stored `ollama` connection serves none. Every read
carries the answer as `served_agents`, and `compatible_agents` is the same list. A scope stored before
this rule is ignored. The connection's page says which agents can use it, and an agent's Change model
dialog offers only the connections that serve it.

#### Scenario: a connection with no Anthropic address does not serve Claude Code
- **GIVEN** an `openai` connection with no Anthropic address and a registered Claude Code agent
- **WHEN** the user reads the connection and previews switching Claude Code onto it
- **THEN** `served_agents` is `["codex"]` and the preview is refused with 409 `PROVIDER_DOES_NOT_REACH_AGENT`

### Requirement: Fill in the Anthropic address of an existing connection

At startup, before the boot reconcile pass, an `openai` remote connection with no Anthropic address
MUST be given one when:

- its base URL is a vendor whose Anthropic address is known (DeepSeek) and Codex does not run on it:
  that address, whose key then waits for approval like any new destination;
- otherwise Claude Code runs on it: its own base URL, which is where Claude Code's requests already
  went.

A connection that has an Anthropic address is left alone, so clearing it later sticks. A failure is
logged and never stops the start.

#### Scenario: a gateway Claude Code runs on keeps working
- **GIVEN** an `openai` connection with no Anthropic address that Claude Code runs on
- **WHEN** Coffer starts
- **THEN** its Anthropic address is its base URL, and Claude Code still runs on it

#### Scenario: a DeepSeek connection gets DeepSeek's Anthropic address
- **GIVEN** an `openai` connection at `https://api.deepseek.com` that Codex does not run on
- **WHEN** Coffer starts
- **THEN** its Anthropic address is `https://api.deepseek.com/anthropic`

### Requirement: Retire the off switch and scope of existing connections

At startup, before the boot reconcile pass, every agent whose `connection_uid` names a switched-off
connection MUST be put back on its own login (Coffer's keys removed from its config, its connection
cleared), and the connection switched on; a scope a connection stored MUST be cleared. A connection
that is on and unscoped is left alone, and a failure is logged and never stops the start. Every
surface MUST refuse to switch a connection off (`RESOURCE_NOT_TOGGLEABLE`); the stored flag stays
readable only so this step can find the connections that were off, and a later release makes the
kind non-toggleable and drops the step.

#### Scenario: an agent on a switched-off connection goes back to its own login
- **GIVEN** a switched-off connection that a Claude Code agent's record names, and a scoped connection
- **WHEN** Coffer starts
- **THEN** the Claude Code agent is on its own login, the first connection is switched on, and the second's scope is cleared

#### Scenario: a connection cannot be switched off
- **GIVEN** a connection a Claude Code agent runs on
- **WHEN** the generic disable route is called for it
- **THEN** it is refused with `RESOURCE_NOT_TOGGLEABLE` and the agent keeps its route

### Requirement: Offer the mainstream vendors as presets

The Add dialog MUST offer these vendors, each with its mark and the addresses its own documentation
gives, and Custom for anything else:

- Anthropic, OpenAI, Google Gemini, DeepSeek, OpenRouter, xAI, Mistral, Groq, Together AI,
  Fireworks AI, Kimi, Zhipu GLM, MiniMax, Qwen, SiliconFlow, Baidu Qianfan, Tencent Hunyuan and
  StepFun;
- the local runtimes Ollama and LM Studio.

A vendor names an Anthropic address only where its documentation gives one for Claude Code. A vendor
whose mainland-China addresses differ (Kimi, Zhipu GLM, MiniMax, Qwen, SiliconFlow) offers a region,
International or Mainland China, which swaps both addresses, and says that a key works only in the
region it was created in. A saved connection reads as its vendor, with its mark, from either region's
addresses.

#### Scenario: a vendor with a Mainland China region swaps both addresses
- **GIVEN** the Add dialog with Kimi picked
- **WHEN** the user picks Mainland China
- **THEN** the addresses become `https://api.moonshot.cn/v1` and `https://api.moonshot.cn/anthropic` (TypeScript acceptance test)
