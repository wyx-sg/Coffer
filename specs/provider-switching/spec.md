# Feature Specification: Provider Switching

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/G9-provider-switching`
**Created**: 2026-06-21
**Status**: Draft

## One-line

A unified **LLM connection** lets users configure a key once (name, wire format,
base URL, encrypted credential, model) and use it BOTH ways: project it into the
matching agent's native config file AND let Coffer's own internal LLM engine run
on it. One connection retires the separate `ModelConfig`/`chat_models` registry,
folding internal-engine model selection into the same record. Coffer's
differentiator over `claude switch` or equivalent per-tool scripting: a unified
registry with governance — Fernet-encrypted credentials, full audit trail, and
an inspectable export/import bundle — not per-tool silos.

## Why

Claude Code and Codex each require their own native config files
(`~/.claude/settings.json`, `~/.codex/config.toml`) with provider-specific keys
and base URLs, and Coffer's internal engine used to keep a SECOND, parallel
model registry (`chat_models`). Switching providers today means editing multiple
files by hand, storing keys in plaintext, and losing the audit trail — and a key
configured for an agent could not be reused by the internal engine. Coffer
centralises connections: configure once, project it to the matching agent
(switch), mark one as the internal engine's default, audit everything.

## Confirmed Decisions

Three decisions were locked before spec was written; do not relitigate them.

### Decision A — single-wire connection, per-agent activation, one internal default

One connection holds `{name, wire_format, base_url, credential_ref, model,
fast_model, wire_api, is_active, internal_default}`. A connection projects ONLY
into agents whose native protocol matches its `wire_format`:

- `anthropic` → Claude Code (`~/.claude/settings.json`)
- `openai` → Codex (`~/.codex/config.toml`)
- `ollama` → internal-only; never projected to any agent

At most one active connection per wire format exists at any time (per-wire
single-active invariant, analogous to the `ModelConfig.is_default` pattern in
the retired chat-model registry). Claude Code and Codex "share" the registry — a
credential ref may be reused across connections — but NOT via one record driving
both agents.

In addition to per-agent activation, a connection MAY carry a single GLOBAL
`internal_default` flag (≤1 across all connections) marking the connection
Coffer's own internal LLM engine uses (memory organizer, reorg, distill).
The third wire `ollama` is internal-only: it never projects to
any agent, and because it has no API key its `credential_ref` is absent — it
needs only a `base_url`. `credential_ref` is therefore OPTIONAL: required for
anthropic/openai, absent for ollama. One connection may be BOTH active (projected
to its wire's agent) AND `internal_default` (used internally) — one key, two
uses.

### Decision B — credential isolation; key never plaintext in native config

Consistent with the existing MCP `credential_refs` pattern and the project's
"credential isolation" principle. The raw key stays in the Fernet vault and is
materialised on demand:

- **Claude Code**: `apiKeyHelper = "coffer provider key --wire anthropic"` in
  `settings.json`. Claude invokes this command to fetch the key. Because Claude
  Code re-invokes `apiKeyHelper` periodically, this design makes a future
  hot-switch nearly free — forward-looking only.
- **Codex**: `env_key = "COFFER_PROVIDER_KEY"` in the `[model_providers.coffer]`
  TOML table. Codex reads the key from that env var at runtime. This PR does NOT
  modify Codex spawning; the user must export the key manually (see Quickstart).
  State plainly: **Codex standalone requires `COFFER_PROVIDER_KEY` to be set in
  the shell; auto env-injection into Coffer-spawned Codex is deferred with
  hot-switch.** This is the accepted cost of Decision B.

The raw key is NEVER written to `settings.json`, `config.toml`, or any other
native config file.

### Decision C — phased; hot-switch is OUT OF SCOPE for this PR

This PR ships: registry + projection + switch op + audit + export/import
wiring.

Hot-switch (mid-session reload of a running Claude Code or Codex process) is a
**separate, later PR** and is explicitly **out of scope here**.

## Amendment 2026-06-22 — Connections are optional overrides; multi-protocol; chat built-in fallback

> Status: Draft. Supersedes the gating in Decision A and the two non-goals noted
> below; recorded after reviewing the shipped UI (PR #187). Cross-ref
> [Provider Switching](../../docs/decisions/provider-switching.md) Amendment.

**Why.** Chat shells out to each agent's OWN runtime — Claude Code via the Claude
Agent SDK, Codex via a `codex app-server` subprocess — and the backend never
requires a Coffer connection (`turn_orchestrator` resolves no credential; the
"no connection" block is a frontend-only guard in `DraftThread.tsx`). A
connection is therefore an OPTIONAL OVERRIDE projected into the agent's native
config, not a prerequisite. The shipped UI wrongly treated it as required
(claude_code showed "还没有连接"; chat blocked with "尚未配置连接"), and codex
chat broke because projection writes `wire_api = "chat"`, which `codex-cli`
0.130 rejects (config fails to load → every turn errors).

- **D1 — Connection is an optional override; built-in is the default.** With no
  connection projected for an agent, it runs on its own built-in model/login.
  The chat surface MUST NOT block on "no connection"; it runs on the built-in
  model. (Removes the `DraftThread` hard guard.)
- **D2 — A connection declares the protocols it supports (multi-select).**
  Replaces single-`wire_format` gating: `protocols ⊆ {anthropic, openai}`. A
  connection is offered to EVERY agent whose native protocol it declares
  (anthropic → Claude Code, openai → Codex), so one key can serve both. `ollama`
  / internal-only remains a separate concern for the internal engine. The
  per-wire single-active invariant becomes **per-protocol single-active**: at
  most one connection is the active override per protocol. Coffer still does NOT
  translate protocols — a connection reaches an agent only if it declares that
  agent's protocol (the endpoint must actually speak it).
- **D3 — Per-agent override selection is the source of truth (Agent page).**
  Each agent picks, on its detail page, which connection (among those declaring
  its protocol) overrides it — or "built-in". This REPLACES the former non-goal
  "no manual per-agent binding". Selecting projects it; "built-in" clears
  Coffer's projection so the agent's own auth/model returns.
- **D4 — Chat model selection is a FIXED choice, not free-form.** The chat
  surface offers a fixed dropdown, never a free-text id. Its options are
  state-dependent: when a connection overrides the agent, the connection's
  introspected models (`POST /models/list-models`); otherwise the agent's
  curated BUILT-IN list (Claude Code: opus / sonnet / haiku; Codex: gpt-5 /
  o-series). The picker MUST NOT read the connection's stored `model` /
  `fast_model` fields (they leave the connection in the E1 amendment); the
  current per-conversation value is always shown so it stays selectable. No
  free-form per-conversation model id (`Conversation.model_id` stays vestigial);
  non-chat models (image / video) are never offered. Changing the
  model/connection happens on the Agent page, not per conversation.
- **D5 — Internal-engine selection is a separate control.** "Which connection
  Coffer's internal engine uses" (`internal_default`) moves OUT of the
  connection card into its own dropdown selector on the Model providers page.
  Connection cards drop the internal-engine badge/star and gain an **edit**
  action (add / edit / delete via one dialog).
- **D6 — Connection dialog gains «测试连接» + «拉取模型».** The add/edit dialog
  surfaces test-connection (`POST /models/test-connection`) and list-models
  (`POST /models/list-models`), reusing the existing introspection service.
  Both MUST accept an inline (not-yet-saved) secret so the user can test/fetch
  before saving; fetched models populate a selectable dropdown.
- **D7 — Codex `wire_api` is selectable; default `responses`.** The connection
  exposes `wire_api ∈ {chat, responses}` in the dialog, defaulting to
  `responses` (codex-cli 0.130 dropped `chat`). Fixes the broken-codex-chat bug.

**Now in scope (were non-goals):** per-agent override selection (D3); chat
built-in fallback (D1); one connection serving multiple agents via declared
protocols (D2).

**Still out of scope:** hot-switch; proxy / failover / format conversion;
anthropic↔openai protocol translation.

## Amendment 2026-06-22b — A connection is a credentialed endpoint; model & protocol leave the connection

> Status: Draft. **Supersedes Decision A's "model on the connection" and the
> earlier amendment's D2 (multi-protocol set).** Recorded after researching
> cc-switch and a design pass with the user. Cross-ref
> [Provider Switching](../../docs/decisions/provider-switching.md) amendment D8/D9.

**Why.** A connection answers "which gateway account" — an endpoint + a key.
*Which model* and *which protocol an agent speaks* are properties of the USE,
not of the account: Claude Code always speaks the Anthropic Messages wire and
Codex always speaks OpenAI, so the agent determines the protocol at projection
time; and the model is picked per agent slot / internal-engine / chat turn.
Carrying `model` and a manually-chosen `wire_format` on the connection forced the
user to answer those questions too early and conflated the account with its uses.

- **E1 — Connection entity slims to `{name, base_url, credential_ref,
  protocol}`.** `model`, `fast_model`, and the manual `wire_format` selector are
  REMOVED from the connection. `wire_api` (Codex chat/responses) likewise moves
  to the Codex binding, not the connection.
- **E2 — `protocol` is DETECTED, not user-entered.** On create/edit Coffer
  probes the endpoint (reusing the introspection path) to classify it as
  `anthropic`-wire, `openai`-wire, or `unknown`. The add dialog therefore shows
  only **name + base_url + key + «测试连接»** — no type selector, no model field.
- **E3 — Model is chosen at the point of use.** Per-agent binding (Agent page
  dual slots → `ANTHROPIC_MODEL` + `ANTHROPIC_SMALL_FAST_MODEL`), the
  internal-engine default selector, and the chat surface each pick a model from
  the chosen connection's fetched models. No model lives on the connection. The
  **internal-engine model** is its own global singleton (one row), read/written
  via `GET`/`PUT /api/v1/internal-engine-config` and audited as
  `internal_engine_model_set`. `resolve_internal_connection()` overlays that
  model onto the resolved `internal_default` connection before the engine builds
  its chat model; while the connection still carries a `model` (until E1 lands),
  an empty internal-engine model falls back to the connection's model.
- **E4 — Projection input = connection (endpoint + key + protocol) + the
  binding (model).** Activating/projecting a connection for an agent reads the
  endpoint/key/protocol from the connection and the model(s) from that agent's
  binding. A connection with no binding for an agent projects nothing.
- **E5 — Compatibility filter, with an honest fallback.** The Agent page offers
  only connections whose detected `protocol` matches the agent's wire. When a
  connection's protocol is `unknown` (probe inconclusive), it is shown to ALL
  agents and the user decides — Coffer does not silently hide a possibly-valid
  connection.
- **Migration (option A — discard):** existing connections drop `model` /
  `fast_model`; their `wire_format` is re-derived as a detected `protocol` (or
  `unknown` pending the next probe). Any model a user had configured is NOT
  carried into a binding — after upgrade the user re-selects models on the Agent
  page. This is the clean break the user chose over a best-effort carry-over.

**Supersedes:** Decision A ("one connection holds … model, fast_model … " and
"a connection projects ONLY into agents whose native protocol matches its
`wire_format`" — now the agent's wire drives projection, and the connection's
protocol is a detected compatibility hint); amendment D2 (multi-protocol set —
already dropped, see [Provider Switching](../../docs/decisions/provider-switching.md)
D8: one gateway for two agents = two connections).

**Still NOT in scope (unchanged):** proxy / hot-switch / protocol conversion.

## Amendment 2026-06-23 — Per-connection compatible agents; per-connection key resolution; agent-keyed activation

> Status: Draft. **Supersedes E5's protocol-based compatibility filter and the
> per-protocol single-active invariant.** Recorded after a design pass with the
> user. Cross-ref [Provider Switching](../../docs/decisions/provider-switching.md).

**Why.** Tying projection to the connection's detected `protocol` cannot express
"this openai-compatible gateway (e.g. agnes) should drive Claude Code." Worse, key
resolution was keyed by `wire + is_active` (`apiKeyHelper = coffer provider key
--wire anthropic`, Codex injected `resolve_active_key(OPENAI)`), so routing such a
connection to the "wrong" wire's agent would silently resolve a DIFFERENT
connection's key — a credential mismatch. The fix decouples *which agents a
connection projects into* from *the wire its endpoint speaks*, and resolves keys
per CONNECTION.

- **F1 — `compatible_agents` on the connection.** A connection carries an explicit
  `compatible_agents ⊆ {claude_code, codex}` (`null` ⇒ the wire default:
  anthropic → `[claude_code]`, openai → `[codex]`, ollama → `[]`, unknown → both).
  The add/edit dialog pre-fills checkboxes from the wire but the user may override
  (route an openai gateway to Claude Code). JSON payload — no DB migration.
- **F2 — Projection writer chosen by AGENT type, not protocol.** A connection
  compatible with `claude_code` writes Claude's `settings.json` (anthropic shape);
  with `codex`, Codex's `config.toml`. `protocol` now drives only model
  introspection and whether a key is required.
- **F3 — Per-connection key resolution.** Claude Code's projected `apiKeyHelper` is
  `coffer provider key --connection <name>` → `GET /providers/{name}/key`, so the
  agent always reads exactly the activated connection's key. Codex's
  `COFFER_PROVIDER_KEY` is the key of the connection active for Codex
  (`resolve_active_key_for_agent(codex)`). The legacy `--wire` helper /
  `/active-key/{wire}` stay for back-compat, resolving by the wire's agent.
- **F4 — Activation is per AGENT TYPE.** Invariant: at most one active connection
  per agent type. Activating a connection projects it into all its compatible
  agents and takes those agents over from any previously-active connection
  (de-projecting it from agents the new one does not cover). `use-builtin/{wire}`
  reverts the agent behind that wire; a connection compatible with multiple agents
  is reverted as a unit (the single `is_active` flag is all-or-nothing).
- **F5 — The connections page drops the per-row "switch."** Activation is
  per-agent and lives on the Agent detail → Overview tab (which filters
  connections by `compatible_agents`). The connections page is the library:
  add / edit / delete + show each connection's compatible agents.

**Supersedes:** E5 (protocol-match compatibility filter — now the explicit
`compatible_agents` set); Decision A / FR-011's per-protocol single-active (now
per-agent-type). **Still NOT in scope:** proxy / hot-switch / protocol conversion.

## Amendment 2026-06-23c — Picking a connection is a draft; test then confirm to switch

> Status: Draft. Recorded after the agnes connection was activated for Claude
> Code with no model bound. Cross-ref
> [Provider Switching](../../docs/decisions/provider-switching.md).

**Why.** Under E3/E4 the model lives on the per-agent binding and activation only
projects the endpoint + key. The Agent page activated a connection the instant it
was picked, with no model bound — so a connection whose endpoint serves its own
model ids (the agnes case: an openai gateway routed to Claude Code) left
`ANTHROPIC_MODEL` unset, Claude Code kept sending its built-in `claude-*` ids to
that endpoint, and every model — in both Coffer's slots and Claude Code's own
`/model` picker — failed with "model may not exist or you may not have access."
The user had no chance to choose a model the endpoint serves, and no signal that
the switch (not their account) was the problem. Activating on a mere dropdown
change also made an unverified endpoint the live config with one click.

- **G1 — Picking a connection / model on the Agent page is a DRAFT.** Selecting a
  connection or a model no longer activates or PATCHes anything; it stages a
  choice. Picking a non-built-in connection introspects its endpoint and stages a
  default model — Claude Code's primary + fast and Codex's single slot all default
  to the endpoint's FIRST returned model — so the user has something to test.
- **G2 — «测试连接» before «确认切换».** A custom connection must pass a
  test-connection probe (`POST /models/test-connection` with the staged model)
  before it can be confirmed. Confirm is disabled until the test for the CURRENT
  draft passes; changing the connection or model resets the test result. «确认切换»
  PATCHes the per-agent binding (model + fast_model) then activates the connection
  — the only step that writes native config. Switching to the built-in login needs
  no test (no endpoint to reach) and confirms straight away.

**Supersedes:** E4's implicit "picking activates immediately" — activation is now
gated behind an explicit test + confirm, and the binding is never left empty.
**Still NOT in scope:** proxy / hot-switch / protocol conversion.

## Amendment 2026-09-09 — The agent's model catalogue comes from the backend

> Status: Draft. **Supersedes D4's "curated BUILT-IN list" and its either/or
> option rule.** Recorded after a live session offered a Claude Code
> conversation only `agnes-*` model ids. Cross-ref
> [Provider Switching](../../docs/decisions/provider-switching.md).

**The defect.** D4's "curated BUILT-IN list" existed only as a hardcoded
constant — `["opus", "sonnet", "haiku"]` — duplicated in
`frontend/src/lib/api/providers.ts` and
`backend/coffer/surfaces/http/channel_wiring.py`. Two copies, no owner, and
stale: Claude Code's `--model` also accepts `fable`, `opusplan` and `default`,
so `fable` was simply unreachable from Coffer — the picker is a fixed dropdown
with no free-text (D4), so an id absent from the constant could not be typed
in either. D4's options rule made it worse by being either/or: when a
connection overrode the agent, the picker showed ONLY that connection's
introspected models and HID the agent's own. Observed live: an `is_active`
openai connection routed to `claude_code` while `~/.claude/settings.json`
carried no Coffer projection at all — the agent was in fact running on its
built-in login — yet the chat offered only `agnes-*` ids, none of which the
agent could use.

- **H1 — The catalogue is a backend surface, per agent, and Coffer names no
  model in it.**
  `GET /api/v1/agent-providers/{agent_key}/models` returns the models one agent can
  be put on. Every entry — id, display name, description — is read back from the
  installed agent, never written into Coffer, because a list written down here
  goes stale on the next CLI release and cannot tell one release of a tier from
  the next. Three sources answer, and their order is the order of the picker:
  the Claude Code executable's embedded catalog of versioned models, which is
  the only place the per-release display names exist; Codex's own `model/list`
  app-server RPC; and each CLI's native config for the local choices only it
  knows about (Claude Code publishes `additionalModelOptionsCache` in
  `~/.claude.json`; Codex's `config.toml` names its configured models). The
  catalogue lists **real models only**: the CLIs' tier **aliases** (`sonnet`,
  `opus`, `haiku`, `fable`, `best`, `sonnet[1m]`, `opus[1m]`, `fable[1m]`,
  `opusplan`) are not offered, because each resolves to a model the list already
  carries — Claude Code itself strips a trailing `[1m]` before comparing two
  model names — so listing both padded the picker with nine label-less
  duplicates sitting beside the models they point at. Nothing becomes
  unreachable: an alias is still accepted wherever a model name is typed
  (`/model <name>`, the agent's own config) and the CLI validates it. Accepted
  cost: `best` and `opusplan` are routing BEHAVIOURS rather than single models,
  so they can only be set by typing the name, not by picking one from a list.
  Each entry carries `id` (passed verbatim to the CLI), `label` and
  `description`. Every source
  degrades to nothing on its own — a missing CLI, a changed bundle layout, an
  unauthenticated or wedged agent costs the models that source would have added
  and nothing else. An unknown `agent_key` is a 404. Contract:
  [`specs/provider-switching/contracts/api.openapi.yaml`](contracts/api.openapi.yaml).
- **H2 — Single source of truth.** The frontend constant is deleted; the
  channel `/model` card reads the same catalogue. The list is owned in one
  place — and owned by the agents themselves — so a newly released model reaches
  every surface with no Coffer release at all.
- **H3 — Options are a UNION, not an either/or.** The chat picker's options are
  the agent's catalogue (H1) ∪ the active connection's introspected models
  (`POST /models/list-models`) ∪ the conversation's current value. D4's ban on
  free-text stands — the picker remains a fixed dropdown, and the current value
  is always selectable. A connection therefore adds ids to the picker instead of
  hiding the agent's own.
- **H4 — The Agent page's model slots stay read-only on the built-in login.**
  Those slots bind a CONNECTION's model (E3/E4): `agent.model` is read only when
  Coffer projects a connection. They now render the catalogue plus a hint that
  the built-in login's model is chosen per conversation, so the read-only state
  is explained rather than looking broken.
- **H5 — Coffer tells the agent which model it is on.** The system-prompt append
  Coffer adds on every turn now states which model Coffer put the agent on — or
  that Coffer set no override — and which ids are available. The motivating
  incident: asked in a real channel session, the agent confidently named a model
  it was not running on, because nothing in its context said otherwise. **Claude
  Code only.** Codex's app-server takes no per-thread instructions — its
  `ThreadSettings` carries approval/sandbox/model/effort and no prompt seam — so
  there is nowhere to put the note without polluting the conversation's first
  user message. Codex gets the accurate catalogue (H1) but not the note.

- **H6 — A connection is only active if the agent's config says so.** `is_active`
  is a row in Coffer's database; what it MEANS is a few keys in a file Coffer
  does not own, which the agent's own CLI, other tooling, the user, and a
  restore from backup all rewrite. Nothing put Coffer's keys back and nothing
  noticed they had gone. At boot Coffer now checks, for each agent type with an
  active compatible connection, whether that agent's native config actually
  carries the projection; when it does not, the flag is CLEARED — the agent is
  on its built-in login and every surface now says so. It heals in one direction
  only: it never writes the projection back, because a flag left from an earlier
  session is no warrant to re-route a user's agent through a gateway they are
  not currently using (the sync post-import hook still projects, since an import
  carries the user's explicit switch). The reverse drift — Coffer's keys present
  while the registry says inactive — is reported, not silently removed.
  Revision 0051 also strips the retired agent types (`cursor` / `opencode` /
  `openclaw` / `hermes`) from connections' `compatible_agents`: revision 0048
  deleted those agents' own rows but left their names inside connections, which
  `ProviderConfig` rejects — so on a real install the first validation after the
  upgrade raised and a working connection became unreadable.

**Supersedes:** D4's curated built-in list (now the backend catalogue) and its
either/or option rule (now the union in H3). D4's fixed-dropdown / no-free-text
rule is unchanged. **Still NOT in scope:** proxy / hot-switch / protocol
conversion.

## Amendment 2026-09-11 — The connection curates WHICH models it offers

> Status: Draft. **Nuances E1/E3's "no model on the connection" — it does not
> reverse it.** Recorded after a design pass with the user. Cross-ref
> [ADR provider-switching](../../docs/decisions/provider-switching.md).

**Why.** E3 moved the model to the point of use, and the 2026-09-09 amendment
made the picker's options a union of everything on offer. Both are right, and
together they hand the user a menu they did not choose: a gateway account
frequently serves dozens of models, of which its owner intends to use two or
three. Nothing narrowed that list, because the only two states the design had
were "one model, fixed on the connection" (too early a choice) and "every model
the endpoint serves" (too many). The middle state — *which* of this endpoint's
models do I actually use — belongs to the account, is stable, and is exactly
what the connection is the right place to record.

- **J1 — `models: list[str]` on the connection: the OFFERED set, not a chosen
  model.** The connection still stores no model it *runs*: E1/E3 stand, and every
  point of use (the per-agent binding, the internal-engine selector, the channel
  `/model` card) still makes the choice. `models` only says which ids that choice
  is offered. **EMPTY means no restriction** — the endpoint's whole catalogue —
  which is the default, what every connection created before revision 0059
  carries, and therefore an upgrade that changes nothing for anyone who does not
  curate.
- **J2 — Curated on the connection's detail page, applied by every picker
  downstream.** The user picks from the live introspection
  (`POST /api/v1/models/list-models`) on the connection itself. A picker
  downstream that offers this connection's models then offers exactly the
  curated set when it is non-empty, and everything the endpoint serves when it
  is empty. This narrows the H3 union's *connection* term; the agent's own
  catalogue term is untouched — a curated set never hides a model the agent can
  reach on its own built-in login.
- **J3 — Ids stay opaque; Coffer still writes down no model name.** The curated
  set is validated for SHAPE only (non-blank ids, deduplicated preserving order,
  a sane cap) and passed verbatim to the vendor. Coffer never checks an id
  against a list of its own — the 2026-09-09 amendment's rule is unchanged, and
  an id the endpoint stops serving is a stale menu entry, not a config error.
- **Wire.** `ProviderOut.models: list[str]`; `ProviderCreate.models: list[str] |
  None` (`null` ⇒ empty); `ProviderPatch.models: list[str] | None`, a
  whole-value replace exactly like `compatible_agents` (`null` leaves it alone,
  `[]` clears the restriction). No new route — create and patch carry it.
- **Audit.** No new event: the curated set is ordinary connection config, so a
  change to it rides the `resource_updated` event `ResourceService.update_config`
  already emits, whose `before`/`after` details carry the config verbatim (the
  provider kind declares no redactor because its config holds no secret).
- **Migration 0059** writes `models: []` into every existing `kind='provider'`
  row, so each connection states its own answer — unrestricted — rather than
  leaning on a reader's default. One-shot, per the house rule: no load-time shim.

**Nuances:** E1/E3 (the model leaves the connection — still true of the CHOSEN
model) and H3 (the picker's union — its connection term is now the curated set
when one exists). **Still NOT in scope:** proxy / hot-switch / protocol
conversion; and Coffer still validates no model id against a list of its own.

## Amendment 2026-09-11b — The agent curates which of its own catalogue it offers

> Status: Draft. **Narrows H1's catalogue at the point of OFFER; it does not
> change what the catalogue is.** Recorded after a design pass with the user.
> Cross-ref [ADR provider-switching](../../docs/decisions/provider-switching.md).

**Why.** H1 made the catalogue the agent's own answer, which was right and
remains right — but that answer is CUMULATIVE and ACCOUNT-BLIND. Claude Code's
embedded catalog runs to nineteen models on a current install, of which this
user's account can actually run nine. The other ten fail the moment they are
picked, and the picker gives no hint which is which.

Whether the ten can be excluded automatically was investigated and they cannot.
Every field of all nineteen entries was compared against the known-good nine:
`pricing` does not separate them (`claude-opus-4-5` and `claude-opus-4-6` are
both `tier_5_25`, one dead and one alive), nor do `capabilities` (the working
`claude-haiku-4-5` carries only `context_management` while the unavailable
`claude-mythos-5-1` carries the full set), nor `knowledge_cutoff`, nor the
context window, nor any version-number rule (opus keeps four versions, sonnet
two). The CLI's own filter runs over `e.config.models` — a SERVER-provided
account config, with `modelAccessCache` in `~/.claude.json` empty on this
machine. **Which models an account may run is an account fact, not a local
one.** A list hardcoded in Coffer would be wrong within a month, because Claude
Code ships new models every few weeks and the user would have no way to tell why
a new one never appeared. So Coffer shows the catalogue and the user ticks it.

- **K1 — Drop the models the binary itself says are dead.** The Claude Code
  bundle carries a second table beside the catalog, pairing a model id with its
  per-provider retirement dates and, for models the CLI silently reroutes, the
  tier it is `remappedTo`. Coffer applies the CLI's own predicate over it: a
  model is gone when it carries a `remappedTo` or when its **`firstParty`**
  retirement date is past. Only `firstParty` — the other columns (bedrock,
  vertex, foundry, …) describe deployments Coffer does not configure and carry
  different dates. Read exactly like the catalog: located structurally, and if
  the anchor ever stops matching the source returns the catalogue **unfiltered**
  rather than a filter built from half a table. This shrinks the list the user
  has to curate, costs nothing, and updates itself on every CLI upgrade.
- **K2 — `models: list[str]` on the agent: which of the catalogue its pickers
  offer.** Stored on `AgentConfig` in the agent's resource row. **EMPTY means
  NOT CURATED** — the whole (K1-filtered) catalogue is offered, exactly as
  before this amendment — which is the default, what every agent registered
  before revision 0060 carries, and what Coffer must do for someone who never
  opens the screen. It never means "no models".
- **K3 — The catalogue route stays whole; the selection is separate
  information.** `GET /api/v1/agent-providers/{agent_key}/models` keeps
  returning the full K1-filtered catalogue: the curation screen renders that
  list and ticks the selection against it, so a narrowed catalogue would make an
  un-ticked model impossible to tick back on. `GET|PUT
  …/models/selection` carries the curated set. Keyed by agent TYPE, like the
  catalogue itself and like the `/model` card, which knows nothing else; the
  set is stored on the first enabled agent resource of that type — the same one
  that supplies the config dir, so catalogue and curation can never come from
  two different agents.
- **K4 — Curation narrows OFFERS, never validation.** Anything that asks "what
  models can this agent be put on" for a PICKER gets the curated set: the web
  picker, the channel `/model` card
  (`ModelSuggestionPort.suggest`), and the per-turn note H5 appends. Nothing
  VALIDATES a model name against it, or against the catalogue — the CLI accepts
  names outside the catalogue entirely (tier aliases, and models newer than the
  installed binary), so `/model <name>` stays raw passthrough and a bad name
  surfaces as the CLI's own error. Ids are stored verbatim, shape-checked only
  (non-blank, deduplicated preserving order, a sane cap), and a curated id the
  catalogue no longer carries is simply not offered.
- **Wire.** `AgentModelSelectionOut.models: list[str]` on `GET`/`PUT`
  `/api/v1/agent-providers/{agent_key}/models/selection`;
  `AgentModelSelectionIn.models: list[str]` replaces the set wholesale, `[]`
  clears it. `PUT` is 404 when no agent of that type is registered — the set
  lives in an agent's config row, so without one there is nowhere to put it.
  Contract: [`specs/channels/contracts/api.openapi.yaml`](../channels/contracts/api.openapi.yaml),
  where the agent-provider routes already live.
- **Audit.** No new event: the curated set is ordinary agent config, so a change
  rides the `resource_updated` event `ResourceService.update_config` already
  emits.
- **Migration 0060** writes `models: []` into every existing `kind='agent'` row,
  so each agent states its own answer — uncurated — rather than leaning on a
  reader's default. One-shot, per the house rule: no load-time shim.

**Nuances:** H1 (the catalogue is still the agent's own answer, now minus what
the agent says is retired) and H4 (the Agent page's built-in-login panel is now
a curation control rather than a read-only list). **Still NOT in scope:**
deriving account entitlement locally — it is not derivable — and Coffer still
writes down no model name of its own.

## Scope

### In scope

- Backend `provider` resource Kind (CRUD via ResourceService → automatic audit
  + automatic inclusion in export/import); credential handling (store secret to
  Fernet vault, keep only ref); projection service (write native config for the
  matching agent); switch / activate operation; `PROVIDER_SWITCHED` audit event;
  export/import wiring (register the kind); key-resolution used by Claude's
  `apiKeyHelper`.
- Internal-engine connection selection: the global `internal_default` flag,
  `set_internal_default(name)` + `resolve_internal_connection()`, the
  `provider_internal_default_set` audit event, consumed by Coffer's internal
  LLM engine (memory organizer / reorg / distill).
- The connection's curated `models` set (the 2026-09-11 amendment): stored on
  `ProviderConfig`, carried by create + patch, backfilled empty by revision 0059,
  and applied by every model picker that offers that connection's models.
- The agent's curated `models` set and the retirement filter (the 2026-09-11b
  amendment): stored on `AgentConfig`, carried by
  `GET|PUT /api/v1/agent-providers/{agent_key}/models/selection`, backfilled
  empty by revision 0060, and applied by every picker that offers the AGENT's
  own catalogue — while the catalogue route itself stays whole.
- Retire the standalone `ModelConfig` registry (model CRUD REST + `coffer model`
  CLI), folding internal-engine model selection into the connection. The
  provider introspection routes (`list-models`, `test-connection`) are KEPT.
- CLI: `coffer provider list|add|show|edit|remove|switch|key|internal-default`
- HTTP API: `/api/v1/providers` (list / create / get / patch / delete) plus
  `/api/v1/providers/{name}/activate` and
  `/api/v1/providers/{name}/internal-default`
- Frontend: a minimal Providers resource page — `DataTable` (name, wire format,
  base URL, model, active) with create / switch / delete actions,
  mirroring the Skills and MCP resource-page pattern.
- Tests across all tiers; acceptance markers tying to the scenarios below; zh
  companion docs for every doc file in this spec bundle.

### Out of scope (explicit non-goals)

- **Hot-switch / running-process reload** — deferred to a later PR.
- **Explicit deactivate / native-config restore** — no "revert to default" op;
  switching overwrites the relevant keys; restoration is a future concern.
- **Provider drift-verify** — spec item 4.9; separate spec.
- **Per-agent provider override beyond wire matching** — a profile whose
  `wire_format` does not match an agent is simply not projected to it; no
  manual per-agent binding.
- **Proxy / failover / format conversion** — no proxying; no fallback chains;
  no anthropic↔openai protocol translation. Wire format is fixed per profile.
- **Auto env-injection of `COFFER_PROVIDER_KEY` into Coffer-spawned Codex** —
  deferred with hot-switch.

## Entity — ProviderProfile (Kind = `"provider"`)

Resource `name` = the profile name (unique within kind; validated by
`validate_name`).

### Config fields (exported `config` dict; deterministic, no machine-local ids)

| Field | Type | Notes |
|---|---|---|
| `wire_format` | `"anthropic" \| "openai" \| "ollama"` | Required. Gates which agent this connection projects to. `ollama` is internal-only — projected to NO agent (`target_for` returns None). |
| `base_url` | `str` | Required (all wires). The upstream LLM endpoint. |
| `credential_ref` | `str \| None` | Optional. Required for anthropic/openai (Fernet vault ref; pattern `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`; conventionally `provider/<name>/key`; multiple connections MAY share one ref). MUST be absent for ollama (no API key). |
| `model` | `str` | Required. Primary model ID → `ANTHROPIC_MODEL` (Claude) / `model` (Codex); the model Coffer's internal engine runs when this is the internal default. |
| `fast_model` | `str \| None` | Optional. `ANTHROPIC_SMALL_FAST_MODEL` (anthropic wire only); ignored for openai. |
| `wire_api` | `"chat" \| "responses"` | Optional, default `"chat"`. openai/Codex only (`[model_providers.*].wire_api`). |
| `is_active` | `bool` | At most one active per `wire_format`. ollama is never projected, so an ollama connection is always inactive. On import, if >1 active for a wire, normalise deterministically (keep most-recently-updated). |
| `internal_default` | `bool` | At most one connection globally is the internal-engine default. On import, if >1, normalise (keep most-recently-updated). |

> This table records the ORIGINAL shape. Amendment E1 removed `model` /
> `fast_model` / `wire_api` and turned `wire_format` into a detected `protocol`;
> the 2026-06-23 amendment added `compatible_agents`; the 2026-09-11 amendment
> added the curated `models` set (empty = unrestricted). The current field list
> is [data-model.md](./data-model.md).

- `audit_redactor`: config holds NO secret (only `credential_ref`); audit shows
  config as-is. Double-check that no secret leaks via `config` or `details`.

## Projection — Writing Native Config

Analogous to `McpInjectionSpec` in `mcp_injection.py`; encode as a small
explicit table.

### anthropic → Claude Code

**File**: `~/.claude/settings.json` (JSON); resolved via
`spec_for(AgentType.CLAUDE_CODE, "settings", cfg_dir)`.

Coffer MANAGES exactly these keys by MERGING into the existing JSON (never full
replace) and writing via `ConfigFileStore.write_text_atomic` (atomic + `.bak`):

| Key path | Value |
|---|---|
| `apiKeyHelper` | `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model` (omit / remove key when `None`) |

`ANTHROPIC_API_KEY` MUST NOT be written (it would override the helper).
Everything else in `settings.json` is preserved; serialised via
`json.dumps(indent=2)` like the MCP JSON path in `mcp_entries.py`.

### openai → Codex

**File**: `~/.codex/config.toml` (TOML); resolved via
`spec_for(AgentType.CODEX, "config", cfg_dir)`.

Coffer MANAGES via `tomlkit` (comment/order-preserving, like the MCP TOML path):

| Key path | Value |
|---|---|
| `model` | `profile.model` |
| `model_provider` | `"coffer"` |
| `[model_providers.coffer].name` | `"Coffer (<profile name>)"` |
| `[model_providers.coffer].base_url` | `profile.base_url` |
| `[model_providers.coffer].wire_api` | `profile.wire_api` (default `"chat"`) |
| `[model_providers.coffer].env_key` | `"COFFER_PROVIDER_KEY"` |

Everything else preserved.

### ollama → (internal only)

An ollama connection projects into NO agent config: `target_for(WireFormat.ollama)`
returns `None`, so activation writes no native config and the connection is never
`is_active`. It is used solely by Coffer's internal engine, reached via
`resolve_internal_connection` when it is the `internal_default`.

## Switch / Activate Operation

`POST /api/v1/providers/{name}/activate` / `coffer provider switch <name>`:

1. Profile must exist; return 404 otherwise.
2. Clear `is_active` on all other profiles of the **same** `wire_format` via
   `ResourceService.update_config`, then set the target's `is_active=true` via
   a second call. The single-process daemon serialises requests so switches
   never interleave.
3. For each ENABLED registered agent whose `AgentType` native wire matches
   `profile.wire_format`, project (write native config). If no matching agent is
   registered, record active but project nothing — **not an error** (report as
   skipped).
4. Emit `provider_switched` audit event with details `{from: <prev_name|null>,
   to: <name>, wire_format, agents: [...projected...]}`.
5. Return `{activated: <name>, projected: [agent...], skipped: [agent...]}`.

NOTE: projection (`_project`) runs BEFORE the activation flip; a native-config
write failure aborts the switch with the registry unchanged.

## Internal engine (Coffer's own LLM)

Separate from per-agent activation, the global `internal_default` flag (≤1 across
all connections) selects the connection Coffer's own internal LLM engine uses —
the memory organizer, reorg, and distill.

- `set_internal_default(name)`: clears `internal_default` on all other
  connections, then sets it on the target (sequential clear-then-set, serialised
  by the single-process daemon so the global single-internal-default invariant
  holds), and emits a `provider_internal_default_set` audit event.
- `resolve_internal_connection() -> ProviderConfig | None`: returns the
  `internal_default` connection's config, or `None` when no connection is marked.
  When `None`, the internal engine (memory organizer / reorg / distill) is a
  clean no-op rather than an error.
- `build_chat_model(connection, ...)`: the internal engine builds its chat model
  from the resolved connection, dispatched by `wire_format` (anthropic / openai /
  ollama). This replaces the retired `ModelConfig` registry's model selection.

A connection may be BOTH `is_active` (projected to its wire's agent) AND
`internal_default` (used internally) — one key, two uses.

## Key Resolution (apiKeyHelper + Codex env)

`coffer provider key --wire <wire_format>`:

1. Find the active profile for the given wire format.
2. Read `credential_ref` → decrypt via `EncryptedCredentialStore.get(ref)`.
3. Print the raw key to **stdout ONLY**. Do NOT log the value.

This is the command Claude Code's `apiKeyHelper` invokes (`--wire anthropic`).
For Codex, the user exports: `export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"`.

## Export / import (reuse, ~zero engine change)

Modeling `provider` as a ResourceService Kind puts it in the export bundle
automatically ([Vault Export and Import](../../docs/decisions/vault-export-import.md)):

- `SyncExporter` lists all kinds → serialises each row to
  `resources/provider/<name>.yaml` via `resource_to_doc`.
- `SyncImporter` reconciles by `(kind, name)`.
- Credentials already travel as Fernet ciphertext at `credentials/<ref>.enc`,
  and only when the user exports with credentials.

Touch points: define the Kind, add a `wire_provider_kind(...)` helper (mirror
`wire_kb_kind` in `surfaces/http/wiring.py`), register into `app.state.kinds`
in `surfaces/http/app.py`. No new migration, no manifest SCHEMA_VERSION bump.

## Audit (reuse)

`ResourceService` create / update already emit `RESOURCE_*` events with
kind-redacted config. Add `PROVIDER_SWITCHED = "provider_switched"` to `AuditEventType`
(`backend/coffer/domain/audit.py`) and emit it from the switch operation via
`AuditService.record(AuditEventType.PROVIDER_SWITCHED.value, ref=ResourceRef(
kind="provider", name=<name>), actor=..., details={...})`. Likewise add
`PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"` and emit it
from `set_internal_default`.

## HTTP API

Hand-written OpenAPI; 005-style — not contract-test-gated; sync manually.
Full spec in [contracts/api.openapi.yaml](./contracts/api.openapi.yaml).

- `GET  /api/v1/providers` → list profiles (`{ "providers": [ ProviderOut, ... ] }`)
- `POST /api/v1/providers` → create (see credential-source rules below)
- `GET  /api/v1/providers/{name}` → one profile
- `PATCH /api/v1/providers/{name}` → update mutable fields (`base_url`,
  `compatible_agents`, `models`, `secret_value`); `wire_format`/`protocol` and
  `credential_ref` are immutable; `secret_value` rotates the stored secret;
  `models` is a whole-value replace (`[]` clears the curated set)
- `DELETE /api/v1/providers/{name}` → delete; guard via
  `find_credential_citations` before removing an owned secret
- `POST /api/v1/providers/{name}/activate` → switch; returns
  `{activated, projected:[agent...], skipped:[agent...]}`
- `POST /api/v1/providers/{name}/internal-default` → set the internal-engine
  default; returns the updated `ProviderOut`

`wire_format` accepts `anthropic`, `openai`, or `ollama` on request and response.

**Credential source rule**: For anthropic/openai, exactly one of `secret_value`
(stored to vault under `provider/<name>/key`, kept as ref) or `credential_ref`
(reuse existing) must be supplied on create; reject if both or neither are
present. For `wire_format=ollama` the credential is OPTIONAL — supply NEITHER
`secret_value` nor `credential_ref` (an ollama connection has no key).

`ProviderOut` NEVER includes the secret; includes `credential_ref`, `is_active`,
and `internal_default`.

## CLI

`coffer provider list|add|show|edit|remove|switch|key|internal-default` with `--json`.

- `add` prompts for / accepts the secret (skipped for an ollama connection,
  which has no key).
- `key` prints the resolved secret (for `apiKeyHelper`); requires `--wire <wire_format>`;
  resolves by the active profile for that wire.
- `internal-default <name>` marks a connection as Coffer's internal-engine
  default (clears any previous one).

## Frontend (minimal)

- `frontend/src/lib/api/providers.ts` — hand-written client + TS types (`types.ts`
  codegen covers only the 001 gateway spec; do NOT expect generated types here).
- A **Model providers** page (route `/model-providers`, in the sidebar's
  RESOURCES group — `provider` is a resource kind with a list UI, so spec ui-shell's
  IA rule puts it there) is the connection library: a `DataTable` (reuse the shared component; see
  SkillsPage / MCP page) with columns name / wire_format / base_url / model /
  active / internal, header action create, and row actions switch /
  set-internal-default / delete, PLUS the Embedding card. The page shows ONLY
  connection (provider + model) info — no agent names, no presets, no modality
  split. Editing a connection is available via the CLI (`coffer provider edit`)
  and the PATCH API, not the web page.
- Per-agent connection + model selection lives on the **agent detail page
  (Overview tab)**, filtered to that agent's wire, reusing the activate API. The
  Model providers page does not bind agents.
- The old `/settings/models`, `/settings/providers` and
  `/settings/llm-connections` routes redirect to `/model-providers`.
- Add `vi.mock` for any new hook in page + table tests.

> **Amendment 2026-06-23 (provider presets).** The add-connection form no longer
> auto-detects the `protocol` from base_url + key. Instead it offers a **provider
> preset** picker (OpenAI / Anthropic / Google Gemini / DeepSeek / Moonshot /
> OpenRouter / Ollama) that fills the endpoint + protocol, plus a **Custom**
> option that reveals a manual protocol selector for any other OpenAI-/Anthropic-
> compatible endpoint. The stored data model is unchanged (`protocol` is still a
> `ProviderConfig` field); only how it is chosen at create time changed. The
> `detect-protocol` probe endpoint stays for other callers but is no longer used
> by the form.

## Acceptance Scenarios

Per `agents/sdd.md`, every scenario in this section is referenced by at least
one test marked `@pytest.mark.acceptance(spec="provider-switching", scenario="…")`
(Python) or `acceptance("provider-switching", "…", …)` (TypeScript).

### Scenario: create an anthropic provider profile with an inline secret

- **Given** no provider named `my-provider` exists,
- **When** the user creates a profile with `wire_format="anthropic"`, a
  `base_url`, `model`, and `secret_value` (the raw API key),
- **Then** the profile is persisted with a `credential_ref` of
  `provider/my-provider/key`, the raw key is stored in the Fernet vault under
  that ref, `ProviderOut` is returned with no secret field, and
  `RESOURCE_CREATED` is audited.

### Scenario: create a profile that reuses an existing credential ref

- **Given** a credential already exists under ref `shared/key`,
- **When** the user creates a profile supplying `credential_ref="shared/key"` (no `secret_value`),
- **Then** the profile is persisted pointing to the existing ref, no new vault
  entry is created, and `ProviderOut` reflects the supplied `credential_ref`.

### Scenario: reject a profile with an unknown wire format

- **Given** the daemon is running,
- **When** the user attempts to create a profile with `wire_format="grpc"`,
- **Then** the request is rejected with `422 Unprocessable Entity` and no
  profile row is created.

### Scenario: reject a profile that supplies neither a secret nor a credential ref

- **Given** the daemon is running,
- **When** the user attempts to create an **anthropic** connection (the
  neither-rule applies to anthropic/openai; ollama legitimately supplies neither)
  without supplying either `secret_value` or `credential_ref`,
- **Then** the request is rejected with `422 Unprocessable Entity` and no
  profile row or vault entry is created.

### Scenario: update a provider profile

- **Given** a provider profile exists,
- **When** the user patches `base_url` and `model` (no `secret_value`),
- **Then** only those fields are updated, `credential_ref` is unchanged, and
  `RESOURCE_UPDATED` is audited.

### Scenario: list provider profiles

- **Given** two provider profiles exist (one anthropic, one openai),
- **When** the user lists all providers,
- **Then** both appear in `ProviderOut[]`, none includes the raw secret, and
  each carries the correct `is_active` flag.

### Scenario: delete a provider profile cleans up its owned credential

- **Given** a profile whose `credential_ref` is `provider/my-provider/key`
  (owned; no other profile shares it),
- **When** the user deletes the profile,
- **Then** the vault entry at that ref is deleted and `RESOURCE_DELETED` is
  audited.

### Scenario: activate an anthropic profile writes Claude Code settings

- **Given** a Claude Code agent is registered and an anthropic profile exists,
- **When** the user activates the profile,
- **Then** `~/.claude/settings.json` contains `apiKeyHelper`,
  `env.ANTHROPIC_BASE_URL`, and `env.ANTHROPIC_MODEL`; if `fast_model` is set,
  `env.ANTHROPIC_SMALL_FAST_MODEL` is present; `ANTHROPIC_API_KEY` is absent;
  and the profile's `is_active` becomes `true`.

### Scenario: an agent's model binding drives the projected model

- **Given** a Claude Code agent is registered with a per-agent model binding
  (`model` + `fast_model`) and an anthropic connection exists,
- **When** the user activates the connection,
- **Then** the projected `env.ANTHROPIC_MODEL` / `env.ANTHROPIC_SMALL_FAST_MODEL`
  come from the AGENT's binding — the model lives at the point of use, not on the
  connection (amendment 2026-06-22b E1/E3/E4). An unbound agent gets no model env
  written, so it runs on its OWN default model.

### Scenario: activate an openai profile writes Codex config

- **Given** a Codex agent is registered and an openai profile exists,
- **When** the user activates the profile,
- **Then** `~/.codex/config.toml` contains `model`, `model_provider = "coffer"`,
  and a `[model_providers.coffer]` table with `base_url`, `wire_api`, and
  `env_key = "COFFER_PROVIDER_KEY"`; the profile's `is_active` becomes `true`.

### Scenario: activating a profile deactivates the previous active profile of the same wire format

- **Given** anthropic profile A is active and anthropic profile B exists,
- **When** the user activates profile B,
- **Then** profile B becomes active and profile A becomes inactive (the
  single-process daemon serialises the clear-then-set so switches never
  interleave).

### Scenario: switch a wire back to the agent built-in login

- **Given** an anthropic connection is active and projected into Claude Code,
- **When** the user switches that wire back to built-in (`POST
  /providers/use-builtin/{wire}`),
- **Then** Coffer's managed keys are removed from the agent's native config so
  it falls back to its own login, and the connection is no longer active; the
  operation is idempotent (a no-op when nothing is active). See
  [Provider Switching](../../docs/decisions/provider-switching.md) amendment D1/D3
  (connections are optional overrides).

### Scenario: activate a profile whose wire matches no registered agent records active but projects nothing

- **Given** no Codex agent is registered and an openai profile exists,
- **When** the user activates the openai profile,
- **Then** the profile's `is_active` becomes `true`, no config file is written,
  and the response carries `skipped: ["codex"]` (or empty `projected`).

### Scenario: switching preserves unrelated native-config keys and writes a .bak backup

- **Given** `~/.claude/settings.json` contains keys that Coffer does not manage
  (e.g. `theme`, `mcpServers`),
- **When** the user activates an anthropic profile,
- **Then** those keys are preserved byte-for-byte in the updated file, a
  `.bak` file is written before the update, and only the Coffer-managed keys
  are changed.

### Scenario: a provider switch is recorded in the audit log

- **Given** an anthropic profile is activated,
- **When** the user queries the audit log,
- **Then** a `provider_switched` entry appears with details `{from, to,
  wire_format, agents}`, timestamp, and actor.

### Scenario: resolve the active provider key for the apiKeyHelper

- **Given** an anthropic profile is active with a known secret stored in the
  vault,
- **When** `coffer provider key --wire anthropic` is executed,
- **Then** the raw key is printed to stdout and the vault key is NOT logged.

### Scenario: a provider profile round-trips through sync export and import

- **Given** a provider profile with a credential ref exists,
- **When** the exporter runs followed by the importer on a clean DB,
- **Then** the profile row is restored with identical `config` fields, the
  credential ciphertext is present at `credentials/<ref>.enc`, and no secret
  is exposed in the bundle's plaintext.

### Scenario: the command line covers create, list, and switch

- **Given** the daemon is running,
- **When** the user runs `coffer provider add`, `coffer provider list --json`,
  and `coffer provider switch` from the CLI,
- **Then** each operation succeeds with the same effect as the HTTP API and
  `list --json` returns machine-readable output.

### Scenario: the connections page lists profiles and their compatible agents

- **Given** the connections page is rendered with two mock connections (each with
  a `compatible_agents` set),
- **When** the page renders,
- **Then** it lists both connections with their compatible-agent chips and shows
  NO per-row "Switch" action — activation is per-agent on the Agent Overview tab
  (TypeScript acceptance test).

### Scenario: route an openai-compatible connection to Claude Code via compatible_agents

- **Given** a Claude Code agent is registered and an `openai`-wire connection is
  created with `compatible_agents = ["claude_code"]` (the agnes case),
- **When** the user activates that connection,
- **Then** it projects into Claude Code's `settings.json` (anthropic shape) with
  `apiKeyHelper = "coffer provider key --connection <name>"`, and
  `GET /providers/{name}/key` returns exactly that connection's key.

### Scenario: list a provider's models

- **Given** a connection being added or edited, with a provider entered (plus
  base URL / credential ref where the provider needs them),
- **When** the provider's models are fetched,
- **Then** Coffer returns the model ids the provider exposes for selection, and
  if none can be listed it returns an empty list with a message so the user can
  still type a model id manually.

### Scenario: test a model connection

- **Given** a connection's provider, model id, and (where required) credential
  ref,
- **When** the connection is tested,
- **Then** Coffer makes a minimal request to the provider and reports success or
  a humanized failure message, without persisting anything.

### Scenario: test or fetch models with an inline unsaved secret

- **Given** the connection dialog is open and no connection (nor its credential
  ref) has been saved yet,
- **When** the user types a raw API key and triggers «测试连接» or «拉取模型»
  (`POST /models/test-connection` / `POST /models/list-models` carrying
  `secret_value` and no `credential_ref`),
- **Then** the introspection service passes the inline key straight to the
  provider without consulting the credential vault, the probe succeeds, and the
  fetched models populate the selectable dropdown (per
  [Provider Switching](../../docs/decisions/provider-switching.md) amendment D6).

### Scenario: create an ollama connection without a credential

- **Given** no connection named `local-llm` exists,
- **When** the user creates a connection with `wire_format="ollama"`, a
  `base_url`, `model`, and neither `secret_value` nor `credential_ref`,
- **Then** the connection persists with `credential_ref` null, no vault entry is
  created, and `ProviderOut` shows `internal_default=false`.

### Scenario: set a connection as the internal engine default

- **Given** two connections exist and none is the internal default,
- **When** the user sets the second as the internal default,
- **Then** its `internal_default` becomes true, the other stays false, and a
  `provider_internal_default_set` audit entry is recorded.

### Scenario: setting a new internal default clears the previous one

- **Given** connection A is the internal default,
- **When** the user sets connection B as the internal default,
- **Then** B's `internal_default` becomes true and A's becomes false (global
  single-internal-default invariant).

### Scenario: choose the model the internal engine runs on

- **Given** a connection is the internal default,
- **When** the operator sets a model on the global internal-engine config
  (`PUT /api/v1/internal-engine-config`),
- **Then** `GET /api/v1/internal-engine-config` returns that model, an
  `internal_engine_model_set` audit entry is recorded, and
  `resolve_internal_connection()` overlays the chosen model onto the resolved
  internal-default connection (the model lives apart from the connection, per
  the amendment below).

### Scenario: the agent's model picker offers a fixed list without free-form entry

- **Given** an agent whose model binding is being edited,
- **When** the model picker is opened,
- **Then** it offers a fixed dropdown of the agent's model catalogue
  (`GET /api/v1/agent-providers/{agent_key}/models`) with no free-text "Custom…"
  entry; and when a connection overrides the agent the dropdown offers that
  connection's introspected models IN ADDITION to the catalogue and the current
  value, never reading the connection's stored `model` field (TypeScript
  acceptance test; union per the 2026-09-09 amendment).

### Scenario: curate which of a connection's models are offered downstream

- **Given** an LLM connection created with `models: ["opus", "sonnet", "opus"]`,
- **When** it is read back, then patched with `models: ["haiku"]`, then patched
  on an unrelated field,
- **Then** the create response, `GET /api/v1/providers/{name}` and the list route
  all report `["opus", "sonnet"]` (stored verbatim, deduplicated, in the order
  chosen); the patch REPLACES the whole set with `["haiku"]`; the unrelated patch
  leaves it alone; and the change is visible in the `resource_updated` audit
  entry the update already emits — no audit event of its own.

### Scenario: a connection with no curated models offers every model the endpoint serves

- **Given** a connection created without `models` (the default, and what every
  connection made before revision 0059 carries),
- **When** it is read back, then curated with `models: ["opus"]`, then patched
  with `models: []`,
- **Then** it reports `[]` — no restriction, the endpoint's whole catalogue — both
  at creation and after the `[]` patch, which clears the curated set.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each managed provider as a Resource of kind
  `provider`, identified by `provider:<name>`.
- **FR-002**: System MUST validate provider config against a kind-specific schema
  (fields: `wire_format`, `base_url`, `credential_ref`, `model`, `fast_model?`,
  `wire_api?`, `is_active`).
- **FR-003**: `ProviderOut` MUST NEVER include the raw secret. `credential_ref`
  and `is_active` MUST be included.

**Credential handling**

- **FR-004**: On create with `secret_value`, System MUST store the raw key under
  `provider/<name>/key` in the Fernet vault and persist only the ref. Exactly
  one of `secret_value` or `credential_ref` must be supplied; both or neither
  must be rejected `422`.
- **FR-005**: On `PATCH` with `secret_value`, System MUST rotate the stored
  secret (overwrite the vault entry) without changing the ref.
- **FR-006**: On delete, if the profile owns its credential ref (no other profile
  cites it), System MUST delete the vault entry via `find_credential_citations`
  guard.

**Projection**

- **FR-007**: System MUST project an activated anthropic profile into
  `~/.claude/settings.json` via `ConfigFileStore.write_text_atomic` (atomic +
  `.bak`), merging only the specified keys, preserving everything else.
  `ANTHROPIC_API_KEY` MUST NOT be written.
- **FR-008**: System MUST project an activated openai profile into
  `~/.codex/config.toml` via `tomlkit` (comment/order-preserving), merging
  only the specified keys, preserving everything else.
- **FR-009**: If `fast_model` is `None`, the key `env.ANTHROPIC_SMALL_FAST_MODEL`
  MUST be omitted or removed from `settings.json`.
- **FR-010**: Domain projection logic MUST be pure (no I/O). The pure functions
  `apply_anthropic_settings(...)` and `apply_codex_provider(...)` in
  `domain/provider/projection.py` return the new native-config TEXT directly;
  `ProviderService._project(...)` calls them and performs the file write.

**Single-active invariant**

- **FR-011**: At most one profile per `wire_format` may have `is_active=true`.
  Activating a profile MUST clear `is_active` on all others of the same wire
  via sequential `ResourceService.update_config` calls, then set the target's
  `is_active=true`. The single-process daemon serialises requests so switches
  never interleave. On import with >1 active for a wire, normalise: keep
  most-recently-updated, set the rest to inactive.

**Switch operation**

- **FR-012**: `POST /api/v1/providers/{name}/activate` MUST apply FR-011, then
  project to all ENABLED registered agents whose native wire matches
  `wire_format`. If no matching agent is registered, record active and return a
  non-empty `skipped` list — NOT an error.
- **FR-013**: System MUST emit audit event with value `"provider_switched"` and
  details `{from, to, wire_format, agents: [...projected...]}`.

**Key resolution**

- **FR-014**: `coffer provider key --wire <wire_format>` MUST find the active
  profile for that wire, decrypt via `EncryptedCredentialStore.get(ref)`, and
  print to stdout only. The raw key MUST NOT be logged. Resolution by profile
  `<name>` is NOT supported on this subcommand; use `--wire` only.

**Export / import**

- **FR-015**: The `provider` kind MUST be registered into `app.state.kinds` so
  `SyncExporter`/`SyncImporter` handle it automatically. No new migration or
  SCHEMA_VERSION bump is needed.

**Audit**

- **FR-016**: `PROVIDER_SWITCHED` (value `"provider_switched"`) MUST be added
  to `AuditEventType` and emitted on every successful switch with `{from, to,
  wire_format, agents}` in details. `RESOURCE_CREATED`, `RESOURCE_UPDATED`,
  `RESOURCE_DELETED` are emitted automatically via `ResourceService`.

**Surfaces**

- **FR-017**: Create, switch, and delete operations MUST be available via (a) the
  REST API, (b) `coffer provider ...` CLI with `--json`, and (c) the web
  Providers page. Editing a profile (PATCH) is available via the REST API and
  the CLI (`coffer provider edit`) only; the web page does NOT require an
  inline edit affordance.
- **FR-018**: The CLI `key` subcommand MUST support `--wire <wire_format>` to
  resolve by the active profile for that wire. Resolution by positional `<name>`
  is NOT supported; `--wire` is the only accepted form.

**Internal engine connection**

- **FR-019**: The `ollama` wire is internal-only and projects to NO agent:
  `target_for(WireFormat.ollama)` MUST return `None`, an ollama connection is
  never `is_active`, and activating it writes no native config.
- **FR-020**: `credential_ref` MUST be optional — required for anthropic/openai,
  absent for ollama. On create, supplying neither `secret_value` nor
  `credential_ref` is valid ONLY for `wire_format=ollama`; for anthropic/openai
  the exactly-one rule of FR-004 stands.
- **FR-021**: At most one connection globally MUST have `internal_default=true`.
  `set_internal_default` MUST clear `internal_default` on all others, then set
  the target (sequential clear-then-set serialised by the single-process
  daemon). On import with >1 internal default, normalise: keep
  most-recently-updated, clear the rest.

  The invariant MUST be enforced by the **database**, not only by that method.
  `internal_default` is an ordinary config field, so the generic resource-update
  route, `coffer provider edit`, and an imported document all write it without
  going through the clear-then-set — and a live vault was found holding two
  flagged connections, which makes "which connection does the internal engine
  use?" a question with no defined answer. A partial unique index over
  `kind` restricted to flagged provider rows makes a second one
  unrepresentable, whatever writes it.
- **FR-022**: `POST /api/v1/providers/{name}/internal-default` MUST set the named
  connection as the internal-engine default (applying FR-021), emit a
  `provider_internal_default_set` audit event, and return the updated
  `ProviderOut`.
- **FR-023**: `resolve_internal_connection()` MUST return the
  `internal_default` connection's `ProviderConfig`, or `None` when no connection
  is marked. When `None`, the internal engine (memory organizer / reorg /
  distill) MUST be a clean no-op rather than an error.
- **FR-024**: The standalone `ModelConfig` registry (model CRUD REST +
  `coffer model` CLI) MUST be retired. The internal engine MUST build its chat
  model from the internal-default connection via `build_chat_model(connection,
  ...)` (dispatched by `wire_format`). The provider introspection routes
  (`POST /api/v1/models/list-models`, `/api/v1/models/test-connection`) MUST be
  retained.

**Curated model set**

- **FR-025**: `ProviderConfig` MUST carry `models: list[str]` — the set of model
  ids the connection OFFERS downstream. An EMPTY list MUST mean no restriction
  (every model the endpoint serves), MUST be the default, and MUST be what every
  connection created before revision 0059 holds. The field MUST NOT be read as a
  chosen model: the choice stays at the point of use (E1/E3). Ids MUST be
  validated for shape only — non-blank, deduplicated preserving order, at most
  200 ids of at most 200 characters — and MUST NEVER be checked against a list of
  model names Coffer writes down.
- **FR-026**: `ProviderCreate.models` (`null` ⇒ empty) and `ProviderPatch.models`
  MUST carry the set; `ProviderOut.models` MUST return it. A `PATCH` MUST replace
  the whole value like `compatible_agents` — `null` leaves it unchanged, `[]`
  clears the restriction — and MUST NOT require a route of its own. A change MUST
  ride the `resource_updated` audit event provider updates already emit.

### Key Entities

- **ProviderProfile**: A Resource of kind `provider`, identified by
  `provider:<name>`. Holds wire format, base URL, optional credential ref
  (absent for ollama), the curated `models` set it offers downstream (empty =
  unrestricted), per-wire `is_active` state, and the global `internal_default`
  flag. Never holds the raw secret, and never a chosen model.
- **`apply_anthropic_settings` / `apply_codex_provider`**: Pure functions in
  `domain/provider/projection.py` that return the new native-config TEXT directly.
  Analogous to `domain/agent/mcp_install.py`'s `apply_install`. No `ProjectionPatch`
  dataclass; no `build_patch()` function.
- **`ProviderService._project`**: Private method in `application/provider/service.py`
  that calls the pure projection functions and performs the file write.
- **`ProjectionTarget` / `target_for(wire)`**: Helper in `domain/provider/projection.py`
  mapping `wire_format` to the target config file descriptor; returns `None` for
  `ollama` (internal-only, no projection).
- **`ProviderService.resolve_active_key(wire)`**: Takes a `wire_format` string
  only; no by-name resolution on this method.
- **`ProviderService.set_internal_default(name)`**: Clears `internal_default` on
  all other connections then sets the target; emits `provider_internal_default_set`.
- **`ProviderService.resolve_internal_connection()`**: Returns the internal-default
  connection's `ProviderConfig`, or `None` (→ the internal engine is a clean
  no-op). `build_chat_model(connection, ...)` builds the internal engine's chat
  model from it, dispatched by `wire_format`.

## Success Criteria

- **SC-001**: From a fresh install, a user can add an anthropic provider profile,
  activate it, and have Claude Code pick up the new endpoint within one
  `coffer provider switch` command.
- **SC-002**: No raw key ever appears in `settings.json`, `config.toml`, or the
  export bundle (`resources/provider/*.yaml`) — verified by an automated scan
  in integration tests.
- **SC-003**: Every Acceptance Scenario is covered by at least one test marked
  `acceptance(spec="provider-switching", scenario="…")`, and
  `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: `make verify` passes locally and in CI.
- **SC-005**: Activating a profile writes the target native-config key set and
  does NOT touch any key outside the defined managed set.
- **SC-006**: With an `internal_default` connection configured, Coffer's internal
  engine (memory organize / reorg / distill) runs on it; with no
  connection marked `internal_default`, the internal engine is a clean no-op.

## Assumptions

- Spec agent-registry (PR #25) is merged; `AgentType`, `AgentConfig`, and
  the agent CRUD + `on_delete` hook are available.
- `EncryptedCredentialStore` (Fernet vault) and `ConfigFileStore.write_text_atomic`
  are available (spec mcp-gateway).
- `tomlkit` is already in the backend's Python dependencies (added by MCP TOML
  path support).
- Coffer runs as a single-user personal tool; no multi-user access control is
  needed beyond the existing `X-Coffer-Token` gate.
- The user's `~/.claude/settings.json` and `~/.codex/config.toml` are writable
  by Coffer. If the file does not exist, Coffer creates it with only the managed
  keys.
- Provider drift-verify (checking whether the live native config matches the
  active profile) is deferred to spec 4.9.
