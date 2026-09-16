# Feature Specification: Provider Switching

**Status**: Accepted

## One-line

An **LLM connection** is a credentialed endpoint — a name, a base URL, a
detected protocol, an encrypted credential and a curated set of the models it
offers. One connection is used both ways: projected into the native config file
of each agent it reaches, and available as the endpoint Coffer's own internal
engine runs on. Coffer's differentiator over per-tool switching scripts is
governance: Fernet-encrypted credentials, a full audit trail, and one registry
that converges across the user's machines.

## Why

Claude Code and Codex each read provider settings from their own native config
file (`~/.claude/settings.json`, `~/.codex/config.toml`) with their own keys and
base URLs. Switching providers by hand means editing several files, storing keys
in plaintext, and losing any record of what changed — and a key configured for
an agent could not be reused by Coffer's own engine. Coffer centralises the
connection: configure once, route it at the agents you mean, mark one as the
internal engine's default, audit everything.

A connection is an **optional override** (D1). An agent with nothing projected
runs on its own built-in login, and no surface may block on "no connection" —
the chat surface offers the agent's own models and runs.

## Decisions

### The connection is a credentialed endpoint

- **E1 — The connection holds `{name, protocol, base_url, credential_ref,
  models}`.** No model it runs, no `fast_model`, no manually-chosen wire format,
  and no `wire_api`: the Codex chat/responses choice belongs to the Codex
  binding. A connection answers "which gateway account", and which model an
  agent runs is a property of the USE, not of the account.
- **E2 — `protocol` says what the endpoint speaks; it does not choose the
  agent, but two things do key off it.** It drives model introspection and
  whether a key is required. Which agent a connection is written into comes
  from its scope, not its wire (F1) — but a keyless (`ollama`) connection
  reaches no agent whatever that scope says (FR-019), and `use-builtin <wire>`
  finds the agent to revert *through* the wire. Both are why the wire cannot
  move under a connection that is switched on (FR-034).
  `anthropic`, `openai`, `ollama` and `unknown` are the values; `unknown` means
  a probe was inconclusive. Coffer can detect it
  (`POST /api/v1/models/detect-protocol`), but the create surface asks for it
  instead: the web dialog offers a **provider preset** (OpenAI / Anthropic /
  Google Gemini / DeepSeek / OpenRouter / Ollama) that fills in the endpoint and
  the protocol, plus a **Custom** option that reveals a manual protocol
  selector, and the CLI takes `--protocol`. The detect route stays for other
  callers.
- **E3 — The model is chosen at the point of use.** The per-agent binding
  (`AgentConfig.model` / `fast_model`), the internal-engine selector and the
  conversation each pick a model from what the chosen connection offers. The
  **internal-engine model** is its own global singleton, read and written via
  `GET` / `PUT /api/v1/internal-engine-config` and audited as
  `internal_engine_model_set`; `resolve_internal_connection()` pairs it with the
  resolved internal-default connection.
- **E3a — The same singleton carries what Coffer does unattended.** Coffer runs
  three passes on its own behalf: aggregation reads the agents' own memory into
  the derived tree (spec [memory](../memory/spec.md) FR-007), organise lets the
  model rewrite that derived digest (FR-030), and tidy lets it rewrite the
  user's own knowledge files (spec [knowledge](../knowledge/spec.md) FR-051).
  Each carries a **switch and an interval** the operator can see and change,
  written through `PUT /api/v1/internal-engine-config/upkeep` — one pass per
  request, each other pass untouched when it is not sent, so a settings surface
  toggling one row cannot write back a stale copy of the other two. An interval
  the operator has not chosen is reported as unchosen ALONGSIDE the default that
  then runs, so the default lives in one place — the worker that owns the pass —
  and raising it later reaches every vault that never chose. A worker picks a
  change up without a restart, and no pass may be scheduled below a floor that
  would busy-loop a model over the user's files. The two passes that write only
  derived files ship ON; tidy, which rewrites the only copy of the user's own
  writing, ships OFF. These settings travel with the model choice (spec
  [vault-sync](../vault-sync/spec.md)): switching a rewriter off is exactly the
  decision a second machine must not be left out of.
- **E4 — Projection input = the connection (endpoint + key + protocol) + the
  agent's binding (model).** A connection with no binding on an agent projects
  no model key at all, so that agent runs on its own default model.

### Which agents a connection reaches

- **F1 — Reach is the resource's framework per-agent `scope`.** The `provider`
  kind declares `supports_scope`
  ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md));
  there is no `compatible_agents` field in the config, in `ProviderCreate` or in
  `ProviderPatch`. A new connection is pre-filled from its wire through the
  kind's `default_scope` hook — both coding agents for a credentialed wire,
  nothing for `ollama` — rather than starting out reaching every agent, which is
  what the framework's unscoped default would have meant. Re-targeting is a
  scope edit (`PUT /api/v1/resources/provider/{name}/scope`,
  `coffer scope set provider:<name> --agents …`), on the surface every scoped
  kind shares. `scope = []` is dormant: the connection reaches no agent, so no
  agent resolves its key.
- **F1a — `enabled` narrows the projection and only the projection.** A disabled
  connection projects into nothing and resolves no key. The CONFIGURED reach is
  still reported without that narrowing, because the two answer different
  questions and one field cannot carry both: folding `enabled` in made a
  disabled connection's reported agent list empty, so switching a connection off
  looked like it had erased the list and switching it back on looked like
  restoring data that was never lost. `enabled` travels on the same payload, so
  a client that wants the intersection takes it — and the two clients that offer
  a connection to act on *now* (the agent's connection picker and the chat model
  picker) MUST.
- **F1b — `is_active` is not redundant with `enabled`.** `enabled` is the user's
  switch on the resource; `is_active` records that this is the connection
  currently *written into* the agents it reaches — a claim about a file on disk,
  which is why the boot self-check (H6) exists to catch it disagreeing.
- **F2 — The projection writer is chosen by AGENT type, not by protocol.** A
  connection reaching `claude_code` writes Claude's `settings.json` (the
  anthropic shape); one reaching `codex` writes Codex's `config.toml`. This is
  how an OpenAI-compatible gateway is routed to Claude Code.
- **E5 — An inconclusive probe hides nothing.** A connection whose protocol is
  `unknown` starts reaching every agent and the user decides; Coffer does not
  silently hide a possibly-valid connection. Coffer still translates nothing
  between protocols — the endpoint must really speak what the agent sends.
- **F5 — The connections page is the library.** It adds, deletes and shows each
  connection's reach; it has no per-row switch, because activation is per agent
  and lives on the Agent detail page's Overview tab.

### Switching an agent onto a connection

- **F4 — Activation is per AGENT TYPE.** At most one active connection per agent
  type. Activating a connection projects it into every agent its scope reaches
  and takes those agents over from any previously-active connection,
  de-projecting that one from agents the new one does not cover.
  `POST /api/v1/providers/use-builtin/{wire}` reverts the agent behind that
  wire; a connection reaching several agents reverts as a unit, because the
  single `is_active` flag is all-or-nothing.
- **G1 — Picking a connection or a model on the Agent page is a DRAFT.** It
  activates nothing and PATCHes nothing; it stages a choice. Picking a
  non-built-in connection introspects its endpoint and stages a default model —
  Claude Code's primary and fast slots and Codex's single slot all default to
  the first model returned — so there is something to test. Without this, a
  connection went live the instant it was picked, with no model bound: Claude
  Code kept sending its own `claude-*` ids to an endpoint that does not serve
  them and every model failed with "model may not exist or you may not have
  access", with nothing saying the switch rather than the account was the
  problem.
- **G2 — Test, then confirm.** A custom connection must pass
  `POST /api/v1/models/test-connection` with the staged model before it can be
  confirmed; confirm stays disabled until the test for the CURRENT draft passes,
  and changing the connection or the model resets the result. Confirming PATCHes
  the per-agent binding and then activates the connection — the only step that
  writes native config. Switching back to the built-in login needs no test.
- **The activate operation.** `POST /api/v1/providers/{name}/activate` /
  `coffer provider switch <name>`:
  1. the connection must exist, else 404;
  2. project into each agent its scope reaches, and de-project the agents the
     previous connection held and this one does not;
  3. clear `is_active` on the connections that held those agents, then set it on
     the target (the single-process daemon serialises requests, so switches
     never interleave);
  4. emit `provider_switched` with `{from, to, protocol, agents}`;
  5. return `{activated, protocol, projected, skipped}`. A connection that
     reaches an agent type no registered agent has is recorded active and
     projects nothing — reported as skipped, not an error.

  Projection runs BEFORE the activation flip, so a failed native-config write
  aborts the switch with the registry unchanged.
- **H6 — A connection is only active if the agent's config says so.**
  `is_active` is a row in Coffer's database; what it MEANS is a few keys in a
  file Coffer does not own, which the agent's own CLI, other tooling, the user
  and a restore from backup all rewrite. At boot Coffer checks, for each agent
  type with an active connection reaching it, whether that agent's native config
  actually carries the projection; when it does not, the flag is CLEARED and
  every surface then says the agent is on its built-in login. It heals in one
  direction only: it never writes the projection back, because a flag left from
  an earlier session is no warrant to re-route a user's agent through a gateway
  they are not currently using. The reverse drift — Coffer's keys present while
  the registry says inactive — is reported, not silently removed.

### Credential isolation

The raw key stays in the Fernet vault and is materialised on demand. It is NEVER
written to `settings.json`, `config.toml`, or any other native config file.

- **Claude Code**: `apiKeyHelper = "coffer provider key --connection <name>"`.
  Claude Code invokes that command to fetch the key, and because it re-invokes
  the helper periodically a future hot-switch is nearly free.
- **Codex**: `env_key = "COFFER_PROVIDER_KEY"` in the `[model_providers.coffer]`
  table. Codex reads the key from that variable, and Coffer materialises it into
  the environment of any Codex process it spawns itself. A Codex the user starts
  in their own shell needs the variable exported there — the accepted cost of
  credential isolation, since Codex offers no helper-command seam.
- **F3 — Keys resolve per CONNECTION.** `GET /api/v1/providers/{name}/key`
  answers for exactly the connection the projected helper names, so routing a
  connection to the "other" wire's agent can never resolve a different
  connection's key. Codex's variable is filled from the connection active for
  Codex. The legacy wire-keyed forms (`coffer provider key --wire <wire>`,
  `GET /api/v1/providers/active-key/{wire}`) remain for `settings.json` files
  written before, and resolve through the wire's agent.

### What a connection offers, and what a picker shows

- **J1 — `models` is the OFFERED set, not a chosen model.** A gateway account
  frequently serves dozens of models of which its owner uses two or three;
  `models` records which. EMPTY means no restriction — the endpoint's whole
  catalogue — and is the default.
- **J2 — Curated on the connection, applied by every picker downstream.** The
  user picks from live introspection (`POST /api/v1/models/list-models`) on the
  connection's own detail page. A picker offering this connection's models then
  offers exactly the curated set when it is non-empty, and everything the
  endpoint serves when it is empty.
- **J3 — Ids stay opaque.** The curated set is validated for SHAPE only
  (non-blank ids, deduplicated preserving order, a sane cap) and passed verbatim
  to the vendor. Coffer never checks an id against a list of its own, so an id
  the endpoint stops serving is a stale menu entry, not a config error.
- **L1 — A curated entry says WHICH KIND of model it is.** `models` is a list of
  `{id, modality}`, where `Modality` is `text` (the default), `embedding`,
  `image`, `video` or `audio`. One endpoint answers for more than chat, and
  without the kind an embedding model could be picked as an agent's chat model.
- **L2 — The STORED modality is the truth.** Coffer infers one in exactly two
  places, both a convenience the user can correct from the connection editor: the
  one-shot migration that converted stored plain-string entries, and endpoint
  introspection, which returns an inferred modality beside each discovered id so
  the editor pre-fills a sensible value. Reading a stored row never re-derives a
  modality.
- **L3 — One inference rule, used in both places.** Lowercase the id, then: an
  id containing `embed` → `embedding`; containing `dall`, `image`, `imagen` or
  `flux`, or carrying a token `sd` / `sd<digits>` → `image`; containing `video`
  or `sora`, or a token `veo` / `veo<digits>` → `video`; containing `whisper` or
  `audio`, or a token `tts` / `tts<digits>` → `audio`; everything else → `text`.
  The long names match as substrings; the short ones match as whole tokens (the
  id split on non-alphanumerics), so an unrelated id is not mis-tagged.
- **L4 — Every CHAT picker narrows the curated set to `text`.** The ids feeding
  `AgentModelCatalogueService.offered()` / `suggest()` — the web picker, the
  channel `/model` card, the turn-time note — and the Codex model catalogue
  Coffer projects, all take the `text` entries and nothing else. A connection
  that curates SOMETHING but nothing `text` offers no chat model rather than
  falling back to the endpoint's whole catalogue.

### The model catalogue

- **D4 — A model is chosen from a fixed list, never typed.** Every Coffer
  surface that offers a model offers a dropdown with no free-text entry, and the
  current value is always among the options so it stays selectable. Non-chat
  models are never offered. A model name is still raw passthrough everywhere the
  CLI accepts one.
- **H1 — The catalogue is a backend surface, per agent, and Coffer names no
  model in it.** `AgentModelCatalogueService` answers, per agent, which models
  that agent can be put on;
  `GET /api/v1/agent-providers/{agent_key}/models` is that answer on the wire.
  Its readers are the web Chat page's picker, the agent detail page, and the
  channel `/model` card, which reads the same service in-process. Every entry —
  id, label, description — is read back from the installed agent, never written
  into Coffer, because a list written down here goes stale on the next CLI
  release. Three sources answer, and their order is the order of the picker:
  Claude Code's embedded **alias table**, Codex's own `model/list` app-server
  RPC, and each CLI's native config for the local choices only it knows (Claude
  Code publishes `additionalModelOptionsCache` in `~/.claude.json`; Codex's
  `config.toml` names its configured models). Every source degrades to nothing
  on its own — a missing CLI, a changed bundle layout, an unauthenticated or
  wedged agent costs the models that source would have added and nothing else.
  An unknown `agent_key` is a 404. Contract:
  [`specs/channels/contracts/api.openapi.yaml`](../channels/contracts/api.openapi.yaml),
  where the agent-provider routes live.
- **H2 — One source of truth.** No surface carries a model list of its own; the
  catalogue is owned in one place, and owned by the agents themselves, so a
  newly released model reaches every surface with no Coffer release at all.
- **M1 — For Claude Code the catalogue IS the alias table.** The ids are the
  aliases the CLI itself accepts (`opus`, `sonnet`, `haiku`, `fable` — whatever
  the table holds), and each label is the display name of the model that alias
  resolves to on a first-party account, so a release that moves an alias
  relabels the picker on its own. Both halves come from one embedded blob,
  located structurally; an anchor that stops matching costs this source
  entirely rather than falling back to something else. The reason is
  entitlement: the versioned catalog is cumulative and account-blind, nothing on
  the machine says which of nineteen models a given account may run, and the
  CLI's own picker offers four aliases and resolves each against the account at
  turn time. Two attempts to have someone curate the remainder — first on the
  agent, then on the channel — were both removed; nothing in Coffer curates an
  agent's models. The accepted cost: a model that is not the current head of its
  family cannot be PICKED from a Coffer surface. It stays typeable, and the
  account's own extra options still reach the picker from `.claude.json`.
- **M2 — Codex answers from its own `model/list`**, and both CLIs' native
  configs still contribute their local choices.
- **K1 — An active connection's curated set IS what a picker offers.** When a
  connection is active, reaches the agent type and curates models, `offered()` /
  `suggest()` answer with those ids, in the user's order, without consulting the
  agent's catalogue: the catalogue describes the account the agent logs into
  itself, and an active connection means the turns do not go there, so mixing
  the two could only offer ids the endpoint rejects. `catalogue()` is unchanged
  and still reports the agent's own models — the full truth the detail page
  renders.
- **K2 — An active connection that curates nothing changes nothing.** Coffer
  knows where the turns go, not what that endpoint serves, and deliberately does
  not ask: this read happens on every card render and every turn, so
  introspection would put a network round trip on the daemon's event loop
  (CODE-034). The agent's own answer stands; curating the connection's set is how
  the user makes it accurate.
- **K3 — No active reaching connection means the agent's own login**, and the
  catalogue is the answer. A provider row Coffer cannot parse degrades to this
  case rather than failing the read.
- **K4 — Codex additionally gets the list in ITS OWN picker.** Projecting a
  curated connection into Codex writes a Coffer-owned catalogue file next to its
  `config.toml` and points `model_catalog_json` at it. That key REPLACES Codex's
  built-in model list (verified against Codex 0.139.0: with a one-model
  catalogue, `model/list` returns exactly that model), which is what is wanted —
  the built-in names are not served by the endpoint the agent now calls.
  De-projection drops the pointer and retires the file, so Codex's own models
  come back; the pointer is dropped iff it names the Coffer-owned file, the same
  ownership discipline `apiKeyHelper` already uses. An uncurated connection
  writes no catalogue, for K2's reason.
  - The file is a **wire contract with another program**: every field Codex's
    parser requires is emitted, pinned by a test. A malformed one does not fail
    loudly — Codex warns and falls back to its built-in list, so the projection
    silently does not take effect.
  - Values Coffer cannot derive for a third-party endpoint each take the least
    committal value. One has a real consequence: `base_instructions` is where
    Codex keeps its ENTIRE agent system prompt, and Coffer writes it empty, so
    Codex sends no `instructions` field. It still sends its permissions, skills
    and environment developer messages and the full tool set, so the agent works,
    but without Codex's persona prompt. Copying that prompt into a Coffer-written
    file would pin one Codex version's prompt and silently override every later
    one; Coffer does not author another product's system prompt.
  - Claude Code has no equivalent. The only thing shaped like one,
    `additionalModelOptionsCache`, is Claude Code's own CACHE of a field from its
    API response; anything written into it is clobbered. So for `claude_code` the
    Coffer-side surfaces stay the only places the model is chosen.
- **H4 — The Agent page offers no model control on the built-in login.** Those
  slots bind a CONNECTION's model (E3/E4), so on the built-in login the panel
  shows no picker and no list — only a line saying where the model is chosen
  instead (per conversation in the Chat page's picker, or with `/model` in a
  channel), so the absence is explained rather than looking broken.
- **H5 — Coffer tells the agent which model it is on.** The system-prompt append
  Coffer adds on every turn states which model Coffer put the agent on — or that
  Coffer set no override — and which ids are available. Asked in a real channel
  session, an agent confidently named a model it was not running on, because
  nothing in its context said otherwise. **Claude Code only**: Codex's
  app-server takes no per-thread instructions, so there is nowhere to put the
  note without polluting the conversation's first user message. Codex gets the
  accurate catalogue, not the note.

### Reasoning effort

- **N1 — The effort travels BESIDE the id, never inside it.** `AgentModel`
  carries `efforts: tuple[str, ...]` — the levels the agent reported, in the
  order it reported them, empty for an agent that takes no such setting — and
  `default_effort`, the level it would use when none is chosen; the `…/models`
  route exposes both. Beside, because that is what the protocols do: the effort
  is its own field on a turn, so folding four levels into the name would
  multiply one model into four entries under names Coffer invented, which J3
  forbids. A reported default is kept only when it is one of the offered levels.
  Nothing is invented for a model that reports none. The stakes are not
  cosmetic: the same prompt on the same model reported 53 reasoning output
  tokens at `low` and 2569 at `xhigh`.
- **O1 — The levels come from the RUNTIME, not from the model.** For Codex they
  are per model, because `model/list` reports `supportedReasoningEfforts` and a
  `defaultReasoningEffort` per entry. For Claude Code they are the same for every
  entry, read once from the installed Claude Agent SDK's own `EffortLevel` alias
  — `ClaudeAgentOptions.effort` renders as the CLI's `--effort` flag — rather
  than written down here. An SDK that declares none yields an empty tuple: the
  controls hide themselves and turns are unchanged.
- **O2 — No default is named for Claude Code.** `ClaudeAgentOptions.effort`
  defaults to `None`, meaning "whatever the CLI decides", and the CLI does not
  say what that is. Prose documentation naming one level is not a
  machine-readable fact, and a picker naming the wrong default is worse than one
  naming none.
- **N2 — Stored per conversation, next to the model.** It goes in the same
  provider-owned `AgentConfig` blob the model already lives in — `cwd`,
  `session_id`, `model`, `effort` — because it is the same kind of fact: a choice
  made for THIS conversation, owned by the provider, belonging neither to the
  agent resource nor to the connection. `PATCH
  /api/v1/chat/conversations/{id}/agent-config` takes `effort` alongside
  `model`; a body that mentions one leaves the other alone, and an empty or null
  value clears the field so the agent runs at its own default.
- **N3 — Codex applies it on the TURN** — `turn/start {threadId, input,
  effort}`, omitted when unset. The alternatives were rejected by experiment:
  `thread/start` ignores an effort field entirely (the response keeps echoing the
  config default, so a thread-level setting would be a control that changes
  nothing while looking like it works), and `thread/settings/update` is refused
  unless the client asks for the `experimentalApi` capability, a dependency
  Coffer will not take on for a field it can set honestly elsewhere.
- **N4 — Coffer validates no level.** Like a model name, the string is passed to
  the CLI as given; the CLI owns that namespace, so a release that renames a
  level or adds a fifth one works the day it ships, and a level an account cannot
  run fails where every other unusable choice fails.
- **O3 — An active connection does not erase the levels.** The ids a picker
  offers are the connection's to answer (K1); the LEVELS are not, because the
  turn still runs through the agent's own runtime whatever endpoint it points at.
  So an id the agent also reports keeps its levels, and one the agent has never
  heard of reports none. The label and description stay the connection's
  business.
- **O4 — Both agents, on every surface that offers a model.** The web Chat
  page's draft bar carries the effort picker the open conversation has (spec
  channels FR-078), and a channel has `/effort`, `/model`'s sibling in every
  respect (spec channels FR-017).

### Codex's `wire_api`

`responses` is the only accepted value, enforced in `AgentConfig`, so anything
else is a 422 the user sees at the moment they set it. Codex 0.139.0 does not
merely ignore `wire_api = "chat"` — it **refuses to load `config.toml`**, so
the agent Coffer projected into has a CLI that will not start. It is not fixed
by mapping at projection time: rewriting the value on the way out would leave
the stored value, and every `AgentOut` reporting it, saying something other than
what Coffer projects, and a setting should not lie about itself. With one legal
value the per-agent override can only hold its own default, which makes it
vestigial; retiring the field is a separate change, since it is on the public
API and the contract.

### Renaming a connection

**A1 — The name is editable, and renaming is one operation.** A connection's
name is its IDENTITY: the vault entry it owns is `provider/<name>/key`, its
audit rows are filed under `provider:<name>`, and the name is written verbatim
into the agent config Coffer projects. A rename therefore moves all of it
together, which is why it is `POST /api/v1/providers/{name}/rename` and not
another `PATCH` field: a patch edits a connection's settings, and a name another
connection already holds must be a 409 rather than an edit that silently merges
two connections.

- The owned vault entry moves with the name — written under the new ref before
  the row moves, the old one removed after, so no step can leave the connection
  pointing at a secret that is not there. A ref that ANOTHER resource also cites
  stays where it is.
- The audit trail follows the resource, and the rename itself is recorded as
  `resource_renamed` with both names.
- An ACTIVE connection is re-projected under the new name, so an agent Coffer put
  on it keeps resolving its key.
- Renaming to the current name is a no-op, not an error.

### Convergence

Modelling `provider` as a resource kind puts a connection into the sync tree
automatically (spec [vault-sync](../vault-sync/spec.md)):

- The exporter writes each row to `resources/provider/<name>.yaml` via
  `resource_to_doc` as step 1 of a converge round; git three-way-merges the tree
  against the remote, and the **applier** puts the resulting difference back, one
  document at a time.
- What an incoming document carries is the connection — identity, description,
  config — and NOT its reach: `enabled` and `scope` are one decision the user
  makes per machine, on the machine. A row that already exists keeps the reach it
  has; a row that has just arrived takes the kind's own default.
- Credentials travel as Fernet ciphertext at `credentials/<ref>.enc`, and only
  when the remote is configured to carry them. The master key never enters the
  repository; it is bootstrapped out-of-band with
  `coffer sync key export` / `import`.
- **Projection is a machine-local side effect, so it is re-derived after every
  round.** `is_active` rides the synced row, but writing the agent's native
  config is something only `activate` / `deactivate` ever did — so a switch made
  on one machine converged the other's registry while its agents kept running on
  stale config. The provider kind's post-import hook re-derives the desired
  projection from the converged rows and applies it idempotently: for each agent
  type with a registered agent, the active connection whose scope reaches it is
  projected, and a type with no active connection is de-projected.
- On a vault holding more than one active connection for an agent type, or more
  than one `internal_default`, the normalisation is deterministic: keep the
  most-recently-updated and clear the rest.

### Audit

`ResourceService` already emits `resource_created` / `resource_updated` /
`resource_deleted` / `resource_renamed` with kind-redacted config, and a change
to the curated model set rides `resource_updated` — the provider kind declares
no redactor, because its config holds no secret. This spec adds
`provider_switched`, `provider_internal_default_set` and
`provider_projection_refused`.

## Scope

### In scope

- The `provider` resource kind (CRUD, audit and sync convergence through
  `ResourceService`); credential handling (store the secret in the Fernet vault,
  keep only the ref); the projection service that writes an agent's native
  config; the switch / activate / use-builtin operations; per-connection key
  resolution for Claude Code's `apiKeyHelper` and Codex's env var.
- Internal-engine selection: the global `internal_default` flag,
  `set_internal_default(name)` + `resolve_internal_connection()`, the
  `provider_internal_default_set` event, and the separate internal-engine model
  and upkeep singleton.
- The connection's curated `models` set, each entry carrying a modality, applied
  by every picker that offers that connection's models.
- The per-agent model catalogue read back from the installed agents, with the
  reasoning levels their runtimes report.
- CLI: `coffer provider list|add|show|edit|rm|switch|use-builtin|key|internal-default`,
  plus the per-agent model binding on `coffer agent edit`.
- HTTP: the `/api/v1/providers` routes, `/api/v1/models/*` introspection, and
  `/api/v1/internal-engine-config[/upkeep]`.
- Frontend: the Model providers library page, a connection detail page with
  Overview and Models tabs, and the per-agent switch on the Agent detail page.
- Tests across all tiers, with acceptance markers tying to the scenarios below.

### Out of scope (explicit non-goals)

- **Hot-switch** — reloading a running Claude Code or Codex process mid-session.
- **Provider drift-verify** — continuously reconciling the live native config
  against the active connection. The boot self-check (H6) is the narrow version
  that exists.
- **Explicit native-config restore** beyond the `.bak` copies projection leaves.
- **Proxy / failover / format conversion** — no proxying, no fallback chains, no
  anthropic↔openai translation. A connection reaches an agent only because the
  user routed it there, and the endpoint must really speak what that agent sends.
- **Curating an agent's own models** — nothing in Coffer narrows what an agent
  reports it can run.
- **Deriving account entitlement locally** — which models an account may run is
  an account fact, and no local source answers it.

## Entity — connection (kind = `"provider"`)

The resource `name` is the connection name, unique within the kind and validated
by `validate_name`. Its config holds `{protocol, base_url, credential_ref,
models, is_active, internal_default}` and never a secret or a chosen model; its
reach is the resource row's `scope`, and its `enabled` switch is the framework's.
The authoritative field list, with types and constraints, is
[data-model.md](./data-model.md).

## Projection — writing native config

Which file is written is decided by the AGENT (F2); the managed key set per
agent, and the ownership markers that make de-projection safe, are in
[data-model.md](./data-model.md). Two rules are normative here:

- Coffer MERGES into the user's existing file and never replaces it. Everything
  outside its managed keys is preserved, and the write is atomic (temp file +
  rename) with a `.bak` copy rotated through three generations.
- A write carries the fingerprint of the content it read and is REFUSED with 409
  `CONFIG_FILE_STALE` — audited as `provider_projection_refused` — when the file
  changed on disk in between, so a concurrent edit by the user or by the agent's
  own CLI is never silently overwritten.

An `ollama` connection projects into no agent: it has no key to write, it is
never `is_active`, and it is used solely by Coffer's internal engine.

## Internal engine

The global `internal_default` flag (at most one across all connections) selects
the connection Coffer's own passes run on.

- `set_internal_default(name)` clears the flag on every other connection, then
  sets it on the target, and emits `provider_internal_default_set`.
- `resolve_internal_connection()` pairs that connection with the global
  internal-engine model, or returns `None` — with which the internal passes are a
  clean no-op rather than an error.
- `build_chat_model(resolved, …)` builds the engine's chat model from the
  resolved pair, dispatched by protocol.

A connection may be BOTH active (projected into the agents it reaches) AND the
internal default — one key, two uses.

## HTTP API

Hand-written OpenAPI, not contract-test-gated; keep it in sync manually. Full
document in [contracts/api.openapi.yaml](./contracts/api.openapi.yaml).

**Connections**

- `GET /api/v1/providers` → `{providers: [ProviderOut, …]}`
- `POST /api/v1/providers` → create (credential-source rule below)
- `GET /api/v1/providers/{name}` → one connection
- `PATCH /api/v1/providers/{name}` → update `base_url`, `protocol`, `models`,
  `secret_value`, `description`. `credential_ref` is immutable; `secret_value`
  rotates the stored secret; `models` is a whole-value replace (`null` leaves it
  alone, `[]` clears the restriction). A `protocol` that actually MOVES is
  refused with `409 PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` while the connection
  is `is_active` (FR-034); re-sending the wire it already has is not a change,
  so a client that submits a whole form is never told its unchanged dropdown is
  a conflict. Reach is not a patch field — it is a scope
  edit, and `ProviderOut.compatible_agents` reports the CONFIGURED reach
  read-only, with `enabled` riding the same payload
- `POST /api/v1/providers/{name}/rename` (`{new_name}`) → rename; 409 when
  another connection holds the name, 404 when this one is absent, a no-op when
  unchanged
- `DELETE /api/v1/providers/{name}` → delete; `find_credential_citations` guards
  the owned secret
- `POST /api/v1/providers/{name}/activate` → switch; returns
  `{activated, protocol, projected, skipped}`
- `POST /api/v1/providers/use-builtin/{wire}` → revert the agent behind that
  wire to its built-in login; idempotent
- `POST /api/v1/providers/{name}/internal-default` → set the internal-engine
  default; returns the updated `ProviderOut`
- `GET /api/v1/providers/{name}/key` → the named connection's key (what the
  projected `apiKeyHelper` calls)
- `GET /api/v1/providers/active-key/{wire}` → the legacy wire-keyed form,
  resolving through that wire's agent

**Introspection** — `POST /api/v1/models/list-models`,
`POST /api/v1/models/test-connection`, `POST /api/v1/models/detect-protocol`.
All three accept an inline `secret_value` so a connection can be tested before
it is saved.

**Internal engine** — `GET` / `PUT /api/v1/internal-engine-config` and
`PUT /api/v1/internal-engine-config/upkeep` (one pass per request).

**Reach** is the framework's own surface:
`GET` / `PUT /api/v1/resources/provider/{name}/scope`.

**Credential source rule**: for `anthropic` / `openai` / `unknown`, exactly one
of `secret_value` (stored under `provider/<name>/key`, kept as a ref) or
`credential_ref` (reuse an existing entry) must be supplied on create; both or
neither is rejected. An `ollama` connection must supply NEITHER.

`ProviderOut` never includes the secret; it carries `credential_ref`,
`compatible_agents`, `models`, `is_active`, `internal_default` and `enabled`.

## CLI

`coffer provider list|add|show|edit|rm|switch|use-builtin|key|internal-default`,
with `--json` on `list`.

- `add <name> --protocol <p> --base-url <url> [--secret <value> |
  --credential-ref <ref>]`. No model is supplied: it is chosen at the point of
  use.
- `edit <name> [--protocol <wire>] [--base-url <url>] [--secret <value>]` —
  `credential_ref` is the one that cannot move. The wire can, subject to
  FR-034.
- `use-builtin <wire>` is `switch`'s other half: it puts that wire's agents
  back on their OWN built-in login, de-projecting Coffer's config and clearing
  the active connection. Idempotent, so it succeeds when nothing was active.
- `rm <name>` removes the connection, and its owned vault entry when nothing
  else cites it.
- `switch <name>` activates the connection for every agent its scope reaches.
- `key --connection <name>` prints that connection's key — what Coffer projects.
  `--wire <wire>` is the legacy form, resolving through the wire's agent. The raw
  value goes to stdout only and is never logged.
- `internal-default <name>` marks the connection Coffer's internal engine uses,
  clearing any previous one.

Re-targeting a connection is `coffer scope set provider:<name> --agents …`, and
a rename is available over HTTP or from the connection's detail page.

## Frontend

- `frontend/src/lib/api/providers.ts` — the client and its types. The enums and
  the activate/deactivate answers come from this spec's generated contract; the
  connection shapes are hand-written.
- **Model providers** (route `/model-providers`, in the sidebar's RESOURCES
  group — spec ui-shell's IA rule puts a resource kind with a list UI there) is
  the connection library: a `DataTable` of name / vendor / base URL / reach, an
  Add action in the header, and Delete per row. There is no per-row switch (F5)
  and no internal-engine badge: which connection Coffer's own engine runs on is a
  fact about the engine, stated where it is set (the internal-engine settings
  panel) and on the connection's own detail header. The **vendor** column and its
  filter are DERIVED from `base_url` by matching it against the preset list
  rather than stored, so an endpoint matching no preset reads as Custom; the
  protocol stays on the detail page, where it answers a question rather than
  sorting a list. The **name** column keeps the user's own name for the
  connection: it is the id the routes and CLI address.
- The connection **detail page** splits into **Overview** and **Models** tabs,
  like agent and MCP-server detail. Its header carries the shared `ScopeControl`
  — the single place the connection's reach and its enabled state are both shown
  and changed. The edit dialog's Name field submits a rename ahead of the patch,
  with the page following the new URL (the route IS the name).
- The **Models** tab is a `DataTable`, one row per model id: id, type and
  offered, with search, a Type filter and an Offered filter. The type is a
  five-value Select pre-filled from what introspection guessed and correctable in
  place; a correction on an already-offered row patches the curated set
  immediately, while one made on a row not offered yet is held on the surface and
  travels into the entry when its Switch is turned on. Empty selection still
  means NO RESTRICTION.
- **A2 — The Models tab introspects on open; there is no "Fetch models"
  button.** Which models an endpoint serves is a fact about the endpoint, exactly
  like an MCP server's tool list, and Coffer lists those the moment the server is
  opened. Making the user press a button first made "the endpoint offers nothing"
  and "nothing asked it" indistinguishable. So the tab probes as it opens, once
  per visit, saying so while it does. A failed probe MUST be visible and
  retryable — the table names the failure and offers a retry — and a failed or
  empty probe leaves the curated selection alone.
- Per-agent connection and model selection lives on the **agent detail page
  (Overview tab)**, filtered to the connections that reach that agent and
  narrowed by `enabled`, as the draft / test / confirm flow of G1–G2. On the
  built-in login it shows no model control, only the line saying where the model
  is chosen (H4).
- The add-connection dialog offers the provider presets of E2 plus Custom, and
  surfaces test-connection and list-models with an inline, not-yet-saved secret.
- The old `/settings/models`, `/settings/providers` and
  `/settings/llm-connections` routes redirect to `/model-providers`.

## Acceptance Scenarios

Per `agents/sdd.md`, every scenario in this section is referenced by at least
one test marked `@pytest.mark.acceptance(spec="provider-switching", scenario="…")`
(Python) or `acceptance("provider-switching", "…", …)` (TypeScript).

### Scenario: create an anthropic provider profile with an inline secret

- **Given** no connection named `my-provider` exists,
- **When** the user creates one with `protocol="anthropic"`, a `base_url` and
  `secret_value` (the raw API key),
- **Then** it is persisted with a `credential_ref` of
  `provider/my-provider/key`, the raw key is stored in the Fernet vault under
  that ref, `ProviderOut` is returned with no secret field, and
  `resource_created` is audited.

### Scenario: create a profile that reuses an existing credential ref

- **Given** a credential already exists under ref `shared/key`,
- **When** the user creates a connection supplying `credential_ref="shared/key"`
  (no `secret_value`),
- **Then** it is persisted pointing at the existing ref, no new vault entry is
  created, and `ProviderOut` reflects the supplied `credential_ref`.

### Scenario: reject a profile with an unknown wire format

- **Given** the daemon is running,
- **When** the user attempts to create a connection with `protocol="grpc"`,
- **Then** the request is rejected with `422 Unprocessable Entity` and no row is
  created.

### Scenario: reject a profile that supplies neither a secret nor a credential ref

- **Given** the daemon is running,
- **When** the user attempts to create an **anthropic** connection (the
  neither-rule applies to anthropic / openai / unknown; ollama legitimately
  supplies neither) without either `secret_value` or `credential_ref`,
- **Then** the request is rejected with `422 Unprocessable Entity` and no row and
  no vault entry are created.

### Scenario: update a provider profile

- **Given** a connection exists,
- **When** the user patches `base_url` (no `secret_value`),
- **Then** only that field is updated, `credential_ref` is unchanged, and
  `resource_updated` is audited.

### Scenario: correcting a mis-probed wire is refused while the connection is live

- **Given** a connection that is switched on and projected into an agent,
- **When** the user patches its `protocol` to a different wire,
- **Then** the request is refused `409` `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`, the stored wire is unchanged, and the message names `coffer provider use-builtin <wire>` as the way out
- **And** re-sending the wire the connection already has is not a change and succeeds, so a client that submits a whole form is never told its unchanged dropdown is a conflict; once the agents are back on their own login, the same patch succeeds (FR-034)

### Scenario: list provider profiles

- **Given** two connections exist (one anthropic, one openai),
- **When** the user lists all connections,
- **Then** both appear in `ProviderOut[]`, none includes the raw secret, and
  each carries the correct `is_active` flag.

### Scenario: delete a provider profile cleans up its owned credential

- **Given** a connection whose `credential_ref` is `provider/my-provider/key`
  (owned; nothing else cites it),
- **When** the user deletes it,
- **Then** the vault entry at that ref is deleted and `resource_deleted` is
  audited.

### Scenario: activate an anthropic profile writes Claude Code settings

- **Given** a Claude Code agent is registered and a connection reaching it
  exists,
- **When** the user activates the connection,
- **Then** `~/.claude/settings.json` contains `apiKeyHelper` naming that
  connection, `env.ANTHROPIC_BASE_URL`, and — when the agent's binding names
  them — `env.ANTHROPIC_MODEL` and `env.ANTHROPIC_SMALL_FAST_MODEL`;
  `ANTHROPIC_API_KEY` is absent; and the connection's `is_active` becomes `true`.

### Scenario: an agent's model binding drives the projected model

- **Given** a Claude Code agent is registered with a per-agent model binding
  (`model` + `fast_model`) and a connection reaching it exists,
- **When** the user activates the connection,
- **Then** the projected `env.ANTHROPIC_MODEL` /
  `env.ANTHROPIC_SMALL_FAST_MODEL` come from the AGENT's binding — the model
  lives at the point of use, not on the connection (E1/E3/E4). An unbound agent
  gets no model env written, so it runs on its OWN default model.

### Scenario: activate an openai profile writes Codex config

- **Given** a Codex agent is registered and a connection reaching it exists,
- **When** the user activates the connection,
- **Then** `~/.codex/config.toml` contains `model` (from the agent's binding),
  `model_provider = "coffer"`, and a `[model_providers.coffer]` table with
  `base_url`, `wire_api = "responses"` and `env_key = "COFFER_PROVIDER_KEY"`;
  and the connection's `is_active` becomes `true`.

### Scenario: activating a profile deactivates the previous active profile of the same wire format

- **Given** connection A is active for an agent type and connection B reaches
  the same agent type,
- **When** the user activates B,
- **Then** B becomes active and A becomes inactive — at most one active
  connection per AGENT TYPE (the single-process daemon serialises the
  clear-then-set so switches never interleave).

### Scenario: switch a wire back to the agent built-in login

- **Given** a connection is active and projected into Claude Code,
- **When** the user switches that wire back to built-in
  (`POST /providers/use-builtin/{wire}`),
- **Then** Coffer's managed keys are removed from the agent's native config so it
  falls back to its own login, and the connection is no longer active; the
  operation is idempotent (a no-op when nothing is active). A connection is an
  optional override (D1).

### Scenario: activate a profile whose wire matches no registered agent records active but projects nothing

- **Given** no Codex agent is registered and a connection reaching only Codex
  exists,
- **When** the user activates it,
- **Then** its `is_active` becomes `true`, no config file is written, and the
  response carries `skipped: ["codex"]` (or empty `projected`).

### Scenario: switching preserves unrelated native-config keys and writes a .bak backup

- **Given** `~/.claude/settings.json` contains keys Coffer does not manage
  (e.g. `theme`, `mcpServers`),
- **When** the user activates a connection reaching that agent,
- **Then** those keys are preserved byte-for-byte in the updated file, a `.bak`
  file is written before the update (the previous `.bak` rotating to `.bak.1`,
  then `.bak.2`; three generations are kept), and only the Coffer-managed keys
  are changed.

### Scenario: projection refuses to overwrite a concurrent edit

- **Given** `~/.claude/settings.json` that the user saves from their editor
  after Coffer has read it and before Coffer writes its projection,
- **When** the projection write runs,
- **Then** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit
  is left intact on disk, no `.bak` is written, and an audit row
  `provider_projection_refused` names the connection, the agent type and the
  file — the caller re-reads and retries.

### Scenario: a provider switch is recorded in the audit log

- **Given** a connection is activated,
- **When** the user queries the audit log,
- **Then** a `provider_switched` entry appears with details
  `{from, to, protocol, agents}`, a timestamp, and an actor.

### Scenario: resolve the active provider key for the apiKeyHelper

- **Given** a connection is active with a known secret stored in the vault,
- **When** its key is resolved — `coffer provider key --connection <name>`, or
  the legacy `--wire anthropic` form,
- **Then** the raw key is printed to stdout and the vault key is NOT logged.

### Scenario: a provider profile round-trips through sync export and import

- **Given** a connection with a credential ref exists on one machine,
- **When** a converge round runs — the exporter writes the connection into the
  tree and the resource **applier** puts that document into the second machine's
  vault,
- **Then** the row lands there with identical `config` fields, the credential
  ciphertext is present at `credentials/<ref>.enc`, and no secret appears
  anywhere in the tree's plaintext. A later edit converges the same way, so the
  second machine ends up with the edited config and description.

### Scenario: the command line covers create, list, switch and revert

- **Given** the daemon is running,
- **When** the user runs `coffer provider add`, `coffer provider list --json`,
  `coffer provider switch` and `coffer provider use-builtin <wire>` from the CLI,
- **Then** each operation succeeds with the same effect as the HTTP API and
  `list --json` returns machine-readable output,
- **And** after the revert the connection is no longer active for its wire, so a
  terminal-only user can undo the switch they made.

### Scenario: the connections page lists profiles and their compatible agents

- **Given** the connections page is rendered with two mock connections whose
  reach differs,
- **When** the page renders,
- **Then** it lists both connections with their endpoints, marks the active one,
  and shows each connection's reach in the Reach column's own control — not as a
  second column repeating it in words — with NO per-row "Switch" action, because
  activation is per-agent on the Agent Overview tab (TypeScript acceptance test).

### Scenario: route an openai-compatible connection to Claude Code with its scope

- **Given** a Claude Code agent is registered and an `openai`-wire connection is
  created and then scoped to `["claude_code"]`,
- **When** the user activates that connection,
- **Then** it projects into Claude Code's `settings.json` (the anthropic shape)
  with `apiKeyHelper = "coffer provider key --connection <name>"`,
  `GET /providers/{name}/key` returns exactly that connection's key, and the
  reported agent set follows the scope.

### Scenario: per-agent key routing follows the connection's scope

- **Given** two activated connections told apart only by their scope — one
  scoped to `claude_code`, one to `codex`,
- **When** each agent's key is resolved,
- **Then** each resolves its own connection's key; disabling a connection, or
  scoping it to no agent, makes it resolve none.

### Scenario: list a provider's models

- **Given** a connection being added or edited, with a protocol entered (plus
  base URL and credential where the endpoint needs them),
- **When** its models are fetched,
- **Then** Coffer returns the model ids the endpoint exposes for selection, each
  with an inferred modality, and if none can be listed it returns an empty list
  with a message so the surface can say what happened.

### Scenario: test a model connection

- **Given** a connection's protocol, a model id, and (where required) a
  credential ref,
- **When** the connection is tested,
- **Then** Coffer makes a minimal request to the endpoint and reports success or
  a humanized failure message, without persisting anything.

### Scenario: test or fetch models with an inline unsaved secret

- **Given** the connection dialog is open and neither the connection nor its
  credential ref has been saved yet,
- **When** the user types a raw API key and triggers test-connection or
  list-models (`POST /models/test-connection` / `POST /models/list-models`
  carrying `secret_value` and no `credential_ref`),
- **Then** the introspection service passes the inline key straight to the
  endpoint without consulting the credential vault, the probe succeeds, and the
  fetched models populate the selectable dropdown.

### Scenario: create an ollama connection without a credential

- **Given** no connection named `local-llm` exists,
- **When** the user creates one with `protocol="ollama"`, a `base_url`, and
  neither `secret_value` nor `credential_ref`,
- **Then** it persists with `credential_ref` null, no vault entry is created, it
  reaches no agent, and `ProviderOut` shows `internal_default=false`.

### Scenario: set a connection as the internal engine default

- **Given** two connections exist and none is the internal default,
- **When** the user sets the second as the internal default,
- **Then** its `internal_default` becomes true, the other stays false, and a
  `provider_internal_default_set` audit entry is recorded.

### Scenario: setting a new internal default clears the previous one

- **Given** connection A is the internal default,
- **When** the user sets connection B as the internal default,
- **Then** B's `internal_default` becomes true and A's becomes false (one
  internal default globally, enforced by the database as well as by the
  operation).

### Scenario: switching the internal engine's connection drops a model it does not serve

- **Given** connection A is the internal default and the internal-engine model
  is one of A's models,
- **When** the user makes connection B the internal default,
- **Then** the internal-engine model is cleared — so
  `resolve_internal_connection()` is `None` until a model is picked again —
  unless B's curated `models` already lists that id, in which case it is kept;
  nothing is probed over the network, and re-setting A, which is already the
  internal default, changes nothing.

### Scenario: switch off and re-time the passes Coffer runs unattended

- **Given** a fresh vault, where aggregation and organise run on their own
  timers and tidy does not,
- **When** the operator switches one pass on or off, or gives it an interval,
  or returns it to its own default (`PUT /api/v1/internal-engine-config/upkeep`,
  one pass per request),
- **Then** that pass's switch and interval change and no other pass's do, the
  reported default interval says what runs while none is chosen, an interval
  below the floor and an unknown pass name are both refused, and the running
  worker picks the change up without a restart.

### Scenario: choose the model the internal engine runs on

- **Given** a connection is the internal default,
- **When** the operator sets a model on the global internal-engine config
  (`PUT /api/v1/internal-engine-config`),
- **Then** `GET /api/v1/internal-engine-config` returns that model, an
  `internal_engine_model_set` audit entry is recorded, and
  `resolve_internal_connection()` pairs the chosen model with the resolved
  internal-default connection (the model lives apart from the connection, E3).

### Scenario: the agent's model picker offers a fixed list without free-form entry

- **Given** an agent whose model is being chosen — on its detail page or in a
  conversation,
- **When** the model picker is opened,
- **Then** it offers a fixed dropdown with no free-text "Custom…" entry and no
  text input: the agent's own catalogue
  (`GET /api/v1/agent-providers/{agent_key}/models`) when it is on its built-in
  login, and the active connection's introspected models when one overrides it —
  never a model field stored on the connection, which carries none (TypeScript
  acceptance test).

### Scenario: curate which of a connection's models are offered downstream

- **Given** a connection created with `models: ["opus", "sonnet", "opus"]`,
- **When** it is read back, then patched with `models: ["haiku"]`, then patched
  on an unrelated field,
- **Then** the create response, `GET /api/v1/providers/{name}` and the list route
  all report `["opus", "sonnet"]` (stored verbatim, deduplicated, in the order
  chosen); the patch REPLACES the whole set with `["haiku"]`; the unrelated patch
  leaves it alone; and the change is visible in the `resource_updated` audit
  entry the update already emits — no audit event of its own.

### Scenario: a connection with no curated models offers every model the endpoint serves

- **Given** a connection created without `models` (the default, and what every
  connection made before the curated set existed carries),
- **When** it is read back, then curated with `models: ["opus"]`, then patched
  with `models: []`,
- **Then** it reports `[]` — no restriction, the endpoint's whole catalogue —
  both at creation and after the `[]` patch, which clears the curated set.

### Scenario: rename a connection and keep its credential, audit trail and projection

**Given** an active connection `acme` with an inline secret, projected into a
registered Claude Code agent,
**When** `POST /api/v1/providers/acme/rename {"new_name": "acme-eu"}` is called,
**Then** the connection answers at `acme-eu` and no longer at `acme`, its
`credential_ref` is `provider/acme-eu/key` with the secret readable there and the
old ref gone, the agent's projected `apiKeyHelper` names `acme-eu`, and the audit
rows recorded under the old name are returned when querying the new one.

### Scenario: reject a rename onto a name another connection already uses

**Given** two connections `acme` and `taken`,
**When** `acme` is renamed to `taken`,
**Then** the response is 409 `RESOURCE_ALREADY_EXISTS` and both connections still
resolve under their original names with their credentials intact.

### Scenario: an agent bound to a renamed connection still resolves its key

**Given** a Claude Code agent running on connection `acme`,
**When** `acme` is renamed,
**Then** `GET /api/v1/providers/<new name>/key` returns the same secret, the
connection the projected config names is the new one, and the connection is
still active and still reaches that agent.

### Scenario: the models table lists the endpoint's models when it opens

**Given** a connection whose endpoint serves a model list,
**When** the Models tab of its detail page is opened,
**Then** the endpoint is introspected without any user action and its model ids
fill the table, each with its own offered/not-offered switch — there is no
"Fetch models" button.

### Scenario: a failed model introspection says so and offers a retry

**Given** a connection whose endpoint refuses the model-list probe,
**When** the Models tab is opened,
**Then** the failure is stated on the surface with a retry control, and the
connection's existing curated selection is left exactly as it was.

### Scenario: curate an embedding model alongside chat models on one connection

- **Given** a connection whose endpoint serves chat and embedding models alike,
- **When** it is created with
  `models: [{"id": "gpt-4o"}, {"id": "text-embedding-3-large", "modality": "embedding"}]`,
  read back, and its endpoint introspected via `POST /api/v1/models/list-models`,
- **Then** the stored set keeps both entries with their modalities — `gpt-4o` as
  `text` (the default) and `text-embedding-3-large` as `embedding` — every read
  returns the modality that was STORED rather than one re-derived at read time,
  and the introspection response carries an inferred modality beside each
  discovered id so the editor can pre-fill it (an id containing `embed` comes
  back as `embedding`, an unrelated id as `text`).

### Scenario: a non-text curated model never reaches a chat model picker

- **Given** an active connection curating one `text` model and one `embedding`
  model,
- **When** the agent's model picker is offered its options
  (`AgentModelCatalogueService.offered()` / `suggest()`, the channel `/model`
  card) and the Codex catalogue is projected into the agent's native config,
- **Then** only the `text` entry appears in any of them — the `embedding` entry
  is offered nowhere as a chat model — while a connection that curates nothing
  still means no restriction.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each managed connection as a Resource of kind
  `provider`, identified by `provider:<name>`.
- **FR-002**: System MUST validate a connection's config against a kind-specific
  schema over `{protocol, base_url, credential_ref, models, is_active,
  internal_default}`, rejecting any other key. The config MUST NOT carry a model
  the connection runs, nor the agents it reaches — reach is the resource row's
  per-agent `scope`.
- **FR-003**: `ProviderOut` MUST NEVER include the raw secret. `credential_ref`,
  `compatible_agents` (the configured reach, read-only), `enabled`, `is_active`
  and `internal_default` MUST be included.

**Credential handling**

- **FR-004**: On create with `secret_value`, System MUST store the raw key under
  `provider/<name>/key` in the Fernet vault and persist only the ref. For
  `anthropic` / `openai` / `unknown`, exactly one of `secret_value` or
  `credential_ref` must be supplied; both or neither MUST be rejected `422`.
- **FR-005**: On `PATCH` with `secret_value`, System MUST rotate the stored
  secret (overwrite the vault entry) without changing the ref.
- **FR-006**: On delete, if the connection owns its credential ref (nothing else
  cites it), System MUST delete the vault entry, guarded by
  `find_credential_citations`.

**Projection**

- **FR-007**: System MUST project into `~/.claude/settings.json` via
  `ConfigFileStore.write_text_atomic` (atomic, with `.bak` rotated through three
  generations), merging only the managed keys and preserving everything else.
  `ANTHROPIC_API_KEY` MUST NOT be written. Every projection write (this one,
  FR-008's, and their de-projections) MUST carry the fingerprint of the content
  it read and MUST be refused with 409 `CONFIG_FILE_STALE` — audited as
  `provider_projection_refused` — when the file changed on disk in between, so a
  concurrent edit is never silently overwritten.
- **FR-008**: System MUST project into `~/.codex/config.toml` via `tomlkit`
  (comment/order-preserving), merging only the managed keys and preserving
  everything else. When the connection curates `text` models it MUST also write
  the Coffer-owned model catalogue and point `model_catalog_json` at it, writing
  the file before the pointer and dropping the pointer before the file; it MUST
  drop that pointer only when it names the Coffer-owned filename.
- **FR-009**: The model keys MUST come from the AGENT's binding. An unset
  `model` or `fast_model` MUST leave the corresponding key out of — or removed
  from — the native config, so the agent runs on its own default. That binding
  MUST be settable without the web UI: `PATCH /api/v1/agents/{name}` carries
  `model` / `fast_model` / `wire_api`, and `coffer agent edit` exposes them as
  `--model` / `--fast-model` / `--wire-api`, with `--clear-fast-model` for the
  explicit null that unbinds the fast slot. It is an option on the verb that
  edits the agent rather than a command of its own, because it is a field of
  the agent.
- **FR-010**: Domain projection logic MUST be pure (no I/O): the `apply_*` /
  `remove_*` functions in `domain/provider/projection.py` take the existing text
  and return the new native-config TEXT; `ProviderProjector` performs the file
  read and write.

**Single-active invariant**

- **FR-011**: At most one connection per AGENT TYPE may have `is_active=true`.
  Activating a connection MUST clear `is_active` on the connections holding the
  agents it reaches, then set the target's, via sequential
  `ResourceService.update_config` calls; the single-process daemon serialises
  requests so switches never interleave. Converging a vault that holds more than
  one active connection for an agent type MUST normalise deterministically: keep
  the most-recently-updated, clear the rest.

**Switch operation**

- **FR-012**: `POST /api/v1/providers/{name}/activate` MUST apply FR-011, then
  project into every ENABLED registered agent the connection's scope reaches. If
  no such agent is registered, it MUST record the connection active and return a
  non-empty `skipped` list — NOT an error.
- **FR-013**: System MUST emit an audit event with value `"provider_switched"`
  and details `{from, to, protocol, agents}`.
- **FR-013a**: `POST /api/v1/providers/use-builtin/{wire}` MUST remove Coffer's
  managed keys from the agent behind that wire and clear the active connection's
  flag, idempotently, reverting a connection that reaches several agents as a
  unit.
- **FR-013b**: At boot, for each agent type with an active connection reaching
  it, System MUST check that the agent's native config actually carries the
  projection and MUST clear `is_active` when it does not. It MUST NOT write the
  projection back; the opposite drift MUST be reported rather than removed.

**Key resolution**

- **FR-014**: `coffer provider key --connection <name>` /
  `GET /api/v1/providers/{name}/key` MUST resolve exactly that connection's
  credential ref, decrypt via `EncryptedCredentialStore.get(ref)`, and print or
  return it without logging the value. The wire-keyed form
  (`--wire <wire>` / `GET /api/v1/providers/active-key/{wire}`) MUST remain for
  back-compat, resolving through the connection active for that wire's agent.

**Convergence**

- **FR-015**: The `provider` kind MUST be registered into the composition root's
  kind table so the sync exporter and the resource applier carry it
  automatically. An incoming document MUST NOT change the local row's reach
  (`enabled` / `scope`), and after a round the kind's post-import hook MUST
  re-derive every agent's projection from the converged rows.

**Audit**

- **FR-016**: `PROVIDER_SWITCHED` (`"provider_switched"`),
  `PROVIDER_INTERNAL_DEFAULT_SET` (`"provider_internal_default_set"`) and
  `PROVIDER_PROJECTION_REFUSED` (`"provider_projection_refused"`) MUST be in
  `AuditEventType` and emitted from the switch, the internal-default operation
  and a refused projection. `resource_created` / `resource_updated` /
  `resource_deleted` / `resource_renamed` are emitted automatically by
  `ResourceService`.

**Surfaces**

- **FR-034**: A connection's `protocol` MUST be correctable — the probe that
  guessed the wire can be wrong, and re-entering the key to fix it is a worse
  answer than editing it. But the wire is **not inert**, so changing it MUST be
  refused while the connection is active, with a conflict that names the way
  out. Two things key off it: a keyless (`ollama`) connection covers no agent
  whatever its scope says (FR-019), and `use-builtin <wire>` finds the agent to
  revert through the wire. Moving the wire of a connection that is currently
  projected would leave the native config Coffer already wrote standing, with
  nothing left that would ever take it off. Silently de-projecting instead MUST
  NOT be the answer: the developer asked to change a field, not to take their
  agents off a gateway. The refusal MUST be reachable on every surface that
  offers the edit — REST, `coffer provider edit`, and the connection's form.

- **FR-017**: Create, switch, revert-to-built-in, rename and delete MUST be
  available via (a) the REST API, (b) `coffer provider …` with `--json` on
  `list`, and (c) the web surfaces — the Model providers library for create and
  delete, the Agent detail page for the switch, the connection's own page for
  the rename. Editing a connection MUST be available over REST, over the CLI
  (`coffer provider edit`) and from its detail page, **including correcting the
  wire** (`--protocol`), which the CLI could not send while its own help called
  the field immutable. Reverting is `coffer provider use-builtin <wire>`: a
  surface that can put an agent onto a Coffer connection and not take it off
  again is half an operation.
- **FR-018**: The CLI `key` subcommand MUST accept `--connection <name>` as its
  primary form and `--wire <wire>` as the back-compat form, and MUST refuse a
  call naming neither.

**Internal engine connection**

- **FR-019**: The `ollama` protocol is internal-only: such a connection MUST
  reach no agent whatever its scope says, MUST never be `is_active`, and
  activating it MUST write no native config. The rule is enforced in
  `application/provider/targets.py::scoped_targets`, which answers `[]` for
  `ollama` **before** the scope is read — it is a rule about projection, not
  about the config's shape, and scope lives outside the config.
- **FR-020**: `credential_ref` MUST be optional — required for `anthropic` /
  `openai` / `unknown`, absent for `ollama`. On create, supplying neither
  `secret_value` nor `credential_ref` is valid ONLY for `ollama`; elsewhere
  FR-004's exactly-one rule stands.
- **FR-021**: At most one connection globally MUST have `internal_default=true`.
  `set_internal_default` MUST clear the flag on all others, then set the target
  (sequential clear-then-set, serialised by the single-process daemon).
  Converging more than one MUST normalise: keep the most-recently-updated.

  The invariant MUST be enforced by the **database**, not only by that method.
  `internal_default` is an ordinary config field, so the generic
  resource-update route, `coffer provider edit`, and an incoming document all
  write it without going through the clear-then-set — and a live vault was found
  holding two flagged connections, which makes "which connection does the
  internal engine use?" a question with no defined answer. A partial unique index
  restricted to flagged provider rows makes a second one unrepresentable,
  whatever writes it.

  A change of connection MUST also DROP the internal-engine model (E3). That
  model is a global singleton with no link to the connection, so carrying the
  previous connection's model across left Coffer's own passes aimed at a model
  the new endpoint has never heard of. The one model kept is one the newly-chosen
  connection CURATES: a curated `models` list is that connection's own catalogue,
  so an id on it is still servable. Nothing is probed to decide — a settings
  write MUST NOT depend on an endpoint being reachable. Cleared, the model falls
  to `None`, `resolve_internal_connection()` returns `None` (FR-023's clean
  no-op), and the model dropdown shows its placeholder over the new connection's
  models. Setting the connection that is ALREADY the internal default MUST change
  nothing. The rule lives in `set_internal_default`, so the HTTP route and
  `coffer provider internal-default` both get it.
- **FR-022**: `POST /api/v1/providers/{name}/internal-default` MUST set the named
  connection as the internal-engine default (applying FR-021), emit a
  `provider_internal_default_set` audit event, and return the updated
  `ProviderOut`.
- **FR-023**: `resolve_internal_connection()` MUST return the internal-default
  connection paired with the global internal-engine model, or `None` when no
  connection is marked or no model is chosen. When `None`, Coffer's internal
  passes MUST be a clean no-op rather than an error.
- **FR-024**: Coffer MUST keep no second model registry: the internal engine
  builds its chat model from the internal-default connection via
  `build_chat_model(resolved, …)`, dispatched by protocol. The introspection
  routes (`POST /api/v1/models/list-models`, `/test-connection`,
  `/detect-protocol`) MUST be retained.

**Curated model set**

- **FR-025**: `ProviderConfig` MUST carry `models` — the set of model ids the
  connection OFFERS downstream (**refined by FR-029** into a list of
  `{id, modality}` objects). An EMPTY list MUST mean no restriction (every model
  the endpoint serves) and MUST be the default. The field MUST NOT be read as a
  chosen model: the choice stays at the point of use (E1/E3). Ids MUST be
  validated for shape only — non-blank, deduplicated preserving order, at most
  200 ids of at most 200 characters — and MUST NEVER be checked against a list of
  model names Coffer writes down.
- **FR-026**: `ProviderCreate.models` (`null` ⇒ empty) and `ProviderPatch.models`
  MUST carry the set; `ProviderOut.models` MUST return it. A `PATCH` MUST replace
  the whole value — `null` leaves it unchanged, `[]` clears the restriction — and
  MUST NOT require a route of its own. A change MUST ride the `resource_updated`
  audit event provider updates already emit.

**Rename**

- **FR-027**: A connection MUST be renamable through a route of its own
  (`POST /api/v1/providers/{name}/rename`), NOT a `ProviderPatch` field. The
  operation MUST move, together: the resource row, the vault entry the
  connection owns (`provider/<name>/key` — unless another resource also cites
  that ref, in which case it MUST be left alone), the `audit_log` rows filed
  under `provider:<old>`, and — when the connection is active — the projection
  in every agent it reaches. It MUST record a `resource_renamed` audit event
  naming both names. A name another connection already holds MUST be refused
  with `RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an absent
  connection MUST be a 404; renaming to the current name MUST be a no-op.

**Model introspection on the connection detail page**

- **FR-028**: The Models tab MUST introspect the endpoint when it opens, without
  a user action, and MUST show that it is doing so. A probe that FAILS MUST say
  so on the surface and offer a retry — it MUST NOT fail silently. A failed or
  empty probe MUST leave the curated `models` selection unchanged, and the
  empty-means-unrestricted semantics of FR-025 MUST be unaffected.

**Model modality**

- **FR-029**: `ProviderConfig.models` MUST be a list of OBJECTS, not of strings:
  each entry is a `CuratedModel` of `{id: str, modality: Modality}`, where
  `Modality` is a `StrEnum` over `text` (the default), `embedding`, `image`,
  `video` and `audio`. The id keeps every property FR-025 gives it (opaque,
  verbatim to the vendor, shape-validated only, deduplicated preserving order,
  empty list = no restriction). The **stored** modality is the truth: Coffer MUST
  infer a modality in exactly two places — the one-shot Alembic migration that
  converts stored plain-string entries, and endpoint introspection (FR-030) —
  both correctable by the user from the connection editor. There MUST be **no
  load-time shim**: reading a stored row MUST NOT re-derive a modality. The
  inference rule, identical in both places, operates on the lowercased id: one
  containing `embed` → `embedding`; containing `dall`, `image`, `imagen` or
  `flux`, or carrying a token `sd` / `sd<digits>` → `image`; containing `video`
  or `sora`, or a token `veo` / `veo<digits>` → `video`; containing `whisper` or
  `audio`, or a token `tts` / `tts<digits>` → `audio`; everything else → `text`.
  The long names MUST match as substrings and the short ones (`sd`, `veo`, `tts`)
  as whole tokens (the id split on non-alphanumerics), so an unrelated id is not
  mis-tagged.
- **FR-030**: `POST /api/v1/models/list-models` MUST return an inferred modality
  alongside each discovered id (by the FR-029 rule), so the connection editor
  pre-fills a sensible value the user can correct; the value it returns is a
  suggestion, never a stored fact. Every CHAT model picker MUST narrow the active
  connection's curated set to modality `text` — the ids fed to
  `AgentModelCatalogueService.offered()` / `suggest()` (the web picker, the
  channel `/model` card, the turn-time note) and the Codex model catalogue Coffer
  projects into the agent's native config. An `embedding`, `image`, `video` or
  `audio` entry MUST NEVER surface as a chat model. A connection curating nothing
  MUST still mean no restriction. `ProviderOut.models`,
  `ProviderCreateRequest.models`, `ProviderPatchRequest.models` and
  `ProviderModelsOut.models` MUST all carry `{id, modality}` objects; patch
  semantics are unchanged (`null` leaves the set alone, `[]` clears the
  restriction).

**The model catalogue**

- **FR-031**: `GET /api/v1/agent-providers/{agent_key}/models` MUST answer, per
  agent type, which models that agent can be put on, read back from the
  installed agent and never written down in Coffer. Each entry MUST carry `id`,
  `label`, `description`, the reasoning `efforts` its runtime reports and the
  `default_effort` it would use, keeping a reported default only when it is one
  of the offered levels. Every source MUST degrade to nothing on its own; an
  unknown `agent_key` MUST be a 404.
- **FR-032**: What a picker is OFFERED MUST be: the active reaching connection's
  curated `text` ids when it curates any, and otherwise the agent's own
  catalogue. That read MUST NOT touch the network. Levels MUST survive it — an
  id the agent also reports keeps the levels the agent reported.
- **FR-033**: Every Coffer surface that chooses a model MUST offer a fixed list
  with no free-text entry, always including the current value. A model name and
  a reasoning level MUST both be passed to the agent verbatim, with no
  validation against a list of Coffer's own.

### Key Entities

- **Connection** (`provider` resource): protocol, base URL, optional credential
  ref (absent for ollama), the curated `models` set it offers downstream (empty =
  unrestricted), `is_active` per agent type, and the global `internal_default`
  flag. Never the raw secret, and never a chosen model. Its reach is the resource
  row's per-agent `scope`.
- **`CuratedModel` / `Modality`**: one curated entry, `{id, modality}`, and the
  `StrEnum` over `text` / `embedding` / `image` / `video` / `audio` it carries
  (FR-029). The modality is Coffer's own note about an opaque id — stored, never
  re-derived at read time — and it is what narrows a connection's curated set to
  the chat models a picker may offer.
- **`ResolvedConnection`**: a connection paired with the model to run on it,
  since the model lives apart from the connection; what
  `resolve_internal_connection()` returns and `build_chat_model` consumes.
- **`apply_anthropic_settings` / `apply_codex_provider`** (and their `remove_*`
  inverses): pure functions in `domain/provider/projection.py` that return the
  new native-config TEXT, analogous to `domain/agent/mcp_install.py`'s
  `apply_install`.
- **`ProviderProjector`**: the application-layer collaborator that reads a
  native config, calls a pure transform, writes it back atomically, refuses a
  stale write, and owns the Codex catalogue file's lifecycle.
- **`ProjectionTarget` / `target_for_agent(agent_type)`**: the agent-keyed map to
  the config file Coffer writes. The map is keyed by AGENT, not by wire — which
  agent a connection is written into comes from its scope, not from its
  protocol (E3/F1).
- **`scoped_targets` / `projection_targets`**: the configured reach, and the
  reach intersected with `enabled` — two questions kept apart on purpose.
- **`AgentModelCatalogueService`**: `catalogue()` (what an agent can run),
  `offered()` (what a picker shows), `efforts()`, `suggest()`.
- **`ProviderService.set_internal_default(name)` /
  `resolve_internal_connection()`**: the global internal-engine flag, the model
  it drops, and the resolved pair the engine runs on.

## Success Criteria

- **SC-001**: From a fresh install, a user can add a connection, bind a model,
  switch an agent onto it, and have that agent pick up the new endpoint.
- **SC-002**: No raw key ever appears in `settings.json`, `config.toml`, or the
  sync tree (`resources/provider/*.yaml`) — verified by an automated scan in
  integration tests.
- **SC-003**: Every acceptance scenario is covered by at least one test marked
  `acceptance(spec="provider-switching", scenario="…")`, and
  `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: `make verify` passes locally and in CI.
- **SC-005**: Activating a connection writes the target native-config key set
  and does NOT touch any key outside the managed set.
- **SC-006**: With an `internal_default` connection and a model configured,
  Coffer's own passes run on it; with neither, they are a clean no-op.
- **SC-007**: A model newly released by an agent's own CLI reaches every Coffer
  picker with no Coffer release.

## Assumptions

- Spec agent-registry is in place: `AgentType`, `AgentConfig`, and agent CRUD
  with its `on_delete` hook are available.
- `EncryptedCredentialStore` (the Fernet vault) and
  `ConfigFileStore.write_text_atomic` are available (spec mcp-gateway).
- `tomlkit` is already a backend dependency (added for the MCP TOML path).
- Coffer runs as a single-user personal tool; no multi-user access control is
  needed beyond the existing `X-Coffer-Token` gate.
- The user's `~/.claude/settings.json` and `~/.codex/config.toml` are writable by
  Coffer. If a file does not exist, Coffer creates it with only the managed keys.
