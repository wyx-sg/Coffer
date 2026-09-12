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
  `compatible_agents ⊆ {claude_code, codex}` (`null` ⇒ the wire default: both
  agents for every credentialed wire, `[]` for ollama, which is internal-only).
  The add/edit dialog pre-fills the checkboxes the same way — every box ticked —
  and the user narrows it (or routes an openai gateway to Claude Code). JSON payload — no DB migration.
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
- **H4 — The Agent page offers NO model control on the built-in login.**
  Those slots bind a CONNECTION's model (E3/E4): `agent.model` is read only when
  Coffer projects a connection. So on the built-in login the panel shows no
  picker and no list — only a line saying where the model is chosen instead (per
  conversation in the chat picker, `/model` in a channel, or that channel's own
  default model), so the absence is explained rather than looking broken.
  (Superseded twice: 2026-09-11b made the panel a curation control, and its
  2026-09-12 withdrawal removed the control altogether — curation belongs to the
  channel, [channels](../channels/spec.md) FR-071.)
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
> reverse it.** **Refined 2026-09-12b:** each curated entry became a
> `{id, modality}` object; every `list[str]` below reads as that list of objects.
> Recorded after a design pass with the user. Cross-ref
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

> Status: **Partly withdrawn 2026-09-12.** K1 (the retirement filter) stands. The
> PER-AGENT curated set K2–K4 introduced is **withdrawn**: curation belongs to
> the surface that has an audience, and it now lives on the CHANNEL
> ([spec channels](../channels/spec.md) FR-071). The bullets below are rewritten
> to say what remains.
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
a new one never appeared. So Coffer shows the catalogue and the user ticks it —
on the CHANNEL since the 2026-09-12 withdrawal below, not on the agent.

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
- **K2 — WITHDRAWN: `models: list[str]` on the agent.** The ticked set was
  stored on `AgentConfig` and narrowed every picker that asked about that agent.
  The premise was right — a cumulative, account-blind catalogue needs the user's
  answer — but the PLACE was wrong: an agent has no audience, and curating it
  narrowed a chat on a phone and a person opening the agent page at once. The
  field, its shape validator and revision 0060's backfill are all gone, stripped
  by **revision 0062** with no load-time shim (house rule). Where the answer
  lives now: `default_model` + `models` on the CHANNEL (channels FR-071).
- **K3 — The catalogue route stays whole, and is now the ONLY one.**
  `GET /api/v1/agent-providers/{agent_key}/models` still returns the full
  K1-filtered catalogue, which is what the agent page renders. `GET|PUT
  …/models/selection` is **removed** along with `AgentModelSelectionIn` /
  `AgentModelSelectionOut`: there is no second question to ask of an agent any
  more. Still keyed by agent TYPE, still answered from the first enabled agent
  resource of that type.
- **K4 — Narrowing an OFFER is the surface's job, never validation.** "What can
  this agent be put on" has one answer — `offered()` / `suggest()` return the
  agent's catalogue (or an active connection's curated set, amendment
  2026-09-11c). A surface that must offer less applies its own range over that
  list: the channel `/model` card does, and it also REFUSES a `/model <id>`
  outside its range. Everywhere else a model name stays raw passthrough — the
  CLI accepts names outside the catalogue entirely (tier aliases, models newer
  than the installed binary), so a bad name surfaces as the CLI's own error.
- **Wire.** Only `AgentModelsOut` remains on
  `GET /api/v1/agent-providers/{agent_key}/models`. Contract:
  [`specs/channels/contracts/api.openapi.yaml`](../channels/contracts/api.openapi.yaml),
  where the agent-provider routes already live.
- **Audit.** Nothing to record: there is no per-agent curated set to change.
- **Migration 0060** wrote `models: []` into every `kind='agent'` row;
  **migration 0062** takes the key back off every one of them, because
  `AgentConfig` forbids extra keys and a row still carrying it would fail to
  validate on load.

**Nuances:** H1 (the catalogue is still the agent's own answer, now minus what
the agent says is retired) and H4 (the Agent page's built-in login now offers no
model control at all — not a picker, not a tick list — just a line saying where
the model is chosen). **Still NOT in scope:**
deriving account entitlement locally — it is not derivable — and Coffer still
writes down no model name of its own.

## Amendment 2026-09-11c — An active connection answers what a picker offers

> Status: Draft. **Nuances 2026-09-11b**: that amendment made a picker show the
> models the ACCOUNT can run; this one says whose account. Recorded after a live
> session where the `/model` card offered `claude-opus-5` to an agent Coffer had
> pointed at a gateway that does not serve it.

**The defect.** `AgentModelCatalogueService` is the one catalogue behind every
surface that offers a model choice, and it only ever asked the AGENT. It knew
nothing about the connection Coffer had activated for that agent. So with an
openai-compatible gateway routed to `claude_code`, the card offered Claude's own
model names, none of which that endpoint serves; tapping one passed the id
straight through to the SDK, which sent it to `ANTHROPIC_BASE_URL` and failed
the turn. Both narrowing rules that existed — the retirement table and the
per-agent curated set (since withdrawn, see 2026-09-11b) — describe the account
the AGENT logs into itself, which is not where those turns were going.

- **K1 — An active connection's curated set IS what a picker offers.** When a
  connection is `is_active`, compatible with the agent type and carries a
  curated model set, `offered()` / `suggest()` answer with those ids, in the
  user's order, without consulting the agent's catalogue. `catalogue()` is
  unchanged and still reports the agent's own models: it is the full truth the
  detail page renders, and what a picker does with it is `offered()`'s
  business.
- **K2 — An active connection that curates nothing changes nothing.** Coffer
  knows where the turns go, not what that endpoint serves, and deliberately does
  not ask: this read happens on every card render and every turn, so
  introspection would put a network round trip on the daemon's event loop
  (CODE-034). The agent's own answer stands; curating the connection's set is
  how the user makes it accurate.
- **K3 — No active compatible connection means the agent's own login**, and the
  catalogue (minus 2026-09-11b's K1 retirement filter) is the answer. A provider row Coffer cannot parse
  degrades to this case rather than failing the read.
- **K4 — Codex additionally gets the list in ITS OWN picker.** Projecting a
  curated connection into Codex writes a Coffer-owned catalogue file next to its
  `config.toml` and points `model_catalog_json` at it. That key REPLACES Codex's
  built-in model list (verified against Codex 0.139.0: with a one-model
  catalogue, `model/list` returns exactly that model), which is what is wanted —
  the built-in names are not served by the endpoint the agent now calls.
  De-projection drops the pointer and retires the file, so Codex's own models
  come back. The pointer is dropped iff it names the Coffer-owned file, the same
  ownership discipline `apiKeyHelper` already uses. An uncurated connection
  writes no catalogue, for K2's reason.
  - The file is a **wire contract with another program**: every field Codex's
    parser requires is emitted, pinned by a test. A malformed one does not fail
    loudly — Codex warns and falls back to its built-in list, so the projection
    silently does not take effect.
  - Values Coffer cannot derive for a third-party endpoint each take the least
    committal value, with the cost of being wrong recorded beside them. One has
    a real consequence: `base_instructions` is where Codex keeps its ENTIRE
    agent system prompt, and Coffer writes it empty — Codex then sends no
    `instructions` field. It still sends its permissions, skills and environment
    developer messages and the full tool set, so the agent works, but without
    Codex's persona prompt. Copying that prompt into a Coffer-written file would
    pin one Codex version's prompt and silently override every later one; Coffer
    does not author another product's system prompt.
  - Claude Code has no equivalent. The only thing shaped like one,
    `additionalModelOptionsCache` in `~/.claude.json`, is Claude Code's own
    CACHE of a field from its API response, refreshed and overwritten from
    there; it is not a contract and anything written into it is clobbered. So
    for `claude_code` the Coffer-side surfaces stay the only places the model is
    chosen.

**Nuances:** 2026-09-11b's K1 retirement filter (still applied whenever the
agent is on its own login) and H1 (the catalogue is read, never authored — now
read from the connection when one is active). **Still NOT in scope:**
endpoint introspection on a picker read, and Coffer still validates no model id
against a list of its own.

## Amendment 2026-09-11d — `wire_api` has one legal value left

> Status: Draft. **Supersedes D7's "`wire_api ∈ {chat, responses}`, selectable".**
> Recorded after checking the installed Codex while validating an unrelated
> change.

**The defect.** `AgentConfig` accepted `wire_api = "chat"` and
`ProviderProjector` wrote it into `[model_providers.coffer]`. Codex 0.139.0
does not merely ignore that value — it **refuses to load `config.toml`**
(`wire_api = "chat" is no longer supported`, naming `responses` as the fix), so
the agent Coffer projected into has a CLI that will not start. Nothing in
Coffer said so: the value was accepted at `PATCH /api/v1/agents/{name}`, stored,
and projected into a file Coffer never reads back, where the failure surfaces as
the agent being broken rather than as a setting being wrong. D7 already knew
`chat` was dropped — it made `responses` the DEFAULT when codex-cli 0.130 went
first — but left the other value selectable.

- **L1 — `responses` is the only accepted value**, enforced in `AgentConfig`, so
  `chat` is a 422 the user sees at the moment they set it. Verified against the
  installed CLI: every other spelling is rejected by Codex's own parser
  (`unknown variant, expected `responses``), and `chat` gets a message of its
  own. This is the one boundary where the failure is still legible; past it,
  Coffer is writing a file only Codex reads.
- **L2 — Not fixed by mapping at projection time.** Rewriting `chat` to
  `responses` on the way out would leave the stored value, and every `AgentOut`
  reporting it, saying something that is not what Coffer projects. A setting
  should not lie about itself.
- **L3 — Migration 0061 flips the rows that already carry it.** One-shot, per
  the house rule: no load-time shim. Revision 0037 did the same flip when
  `wire_api` lived on the CONNECTION; 0040 then moved the field onto the agent,
  and the agent PATCH path accepted `chat` right up to this change, so those
  rows were never covered. Flipping rather than stripping keeps what the setting
  MEANT to express — use Codex's Responses API — as the one thing it can now
  say.

**Note, not a decision:** with a single legal value the per-agent override can
only ever hold its own default, which makes it vestigial. Retiring the field is
a separate change — it is on the public API and the OpenAPI contract — and is
deliberately NOT done here.

## Amendment 2026-09-12 — A connection can be renamed; its models list themselves

> Status: Draft. Adds a rename operation; **supersedes the "name is immutable"
> assumption** the edit dialog encoded, and the Models tab's manual fetch.

**A1 — The name is editable, and renaming is one operation.** A connection's
name is the only handle the user has on it, and it was the one field the edit
dialog refused to change. It is also its IDENTITY: the vault entry it owns is
`provider/<name>/key`, its audit rows are filed under `provider:<name>`, and the
name is written verbatim into the agent config Coffer projects (Claude Code's
`apiKeyHelper` → `coffer provider key --connection <name>`, Codex's provider
`display_name`). A rename therefore MUST move all four together, which is why it
is `POST /api/v1/providers/{name}/rename` and not another `PATCH` field: a patch
edits a connection's settings, and a name that another connection already holds
must be a 409 rather than an edit that silently merges two connections.

- The owned vault entry moves with the name — written under the new ref before
  the row moves, the old one removed after, so no step can leave the connection
  pointing at a secret that is not there. A ref that ANOTHER resource also cites
  stays where it is: renaming it would break that other citer.
- The audit trail follows the resource. The log says what happened to a
  connection, and after a rename that is still the same connection, so stranding
  its history under a name that no longer resolves would lose it; the rename
  itself is recorded as `resource_renamed` with the old and new names, so
  nothing is erased.
- An ACTIVE connection is re-projected under the new name, so an agent Coffer
  put on it keeps resolving its key instead of calling the shim with a
  connection that no longer exists.
- Renaming to the current name is a no-op, not an error.

**A2 — The Models tab introspects on open; there is no "Fetch models" button.**
Which models an endpoint serves is a fact about the endpoint, exactly like the
tool list of an MCP server — and Coffer lists those the moment you open the
server. Making the user press a button first meant the common case (open the
tab, see nothing, wonder whether the endpoint offers nothing or was never
asked) was indistinguishable from an empty endpoint. So the tab probes as it
opens, once per visit, with the table saying it is loading while it does.

- A failed probe MUST be visible and retryable: the table names the failure and
  offers a retry. Silence is not an acceptable outcome of an automatic fetch.
- A failed or empty probe still MUST leave the curated selection alone, and the
  EMPTY-selection semantics are unchanged: empty means no restriction — every
  model the endpoint serves.

**A3 — Two surface corrections that follow from what each page is for.**

- The internal-engine badge is gone from the model-providers LIST row. That page
  manages providers; which one Coffer's own engine happens to run on is a fact
  about the engine, and it is stated where it is set (the internal-engine
  settings panel) and on the connection's own detail header.
- The detail header now carries the shared `ScopeControl` instead of a read-only
  enabled/disabled badge: the list could disable a connection and its own page
  could not. `provider` declares no per-agent scope, so the control renders its
  two-segment Disabled/Enabled fallback — and it is now the single place that
  state is both shown and changed.

## Amendment 2026-09-12b — A curated model says WHICH KIND of model it is

> Status: Draft. **Refines J1's `models: list[str]`** into a list of objects; the
> curated set's meaning (the OFFERED set, empty = no restriction) is unchanged.

**Why.** A provider endpoint serves more than chat models. The same base URL and
the same key answer for embedding, image, video and audio models, and the
curated set said nothing about which was which — so every id the user curated
was offered to every surface that asked, and an embedding model could be picked
as an agent's chat model. A curated entry now says which KIND of model it is, so
a picker asks for the kind it needs instead of offering every id to every
surface.

- **L1 — `models: list[CuratedModel]`, where `CuratedModel = {id, modality}`.**
  `Modality` is a `StrEnum` with five values — `text` (the default),
  `embedding`, `image`, `video`, `audio`. The id keeps every property J3 gave it:
  opaque, verbatim to the vendor, validated for shape only. The modality is
  Coffer's own note about the id, not something the vendor told it.
- **L2 — The STORED modality is the truth; nothing infers one at read time.**
  Coffer infers a modality in exactly two places, both a convenience the user can
  correct from the connection editor: the one-shot Alembic migration that
  converts stored plain-string entries, and endpoint introspection
  (`POST /api/v1/models/list-models`), which returns an inferred modality
  alongside each discovered id so the editor pre-fills a sensible value. There is
  **no load-time shim** — reading a stored row never re-derives a modality, per
  the house rule that a migration is one-shot.
- **L3 — One inference rule, used in both places.** Lowercase the id, then: an id
  containing `embed` → `embedding`; containing `dall`, `image`, `imagen` or
  `flux`, or carrying a token `sd` / `sd<digits>` → `image`; containing `video`
  or `sora`, or a token `veo` / `veo<digits>` → `video`; containing `whisper` or
  `audio`, or a token `tts` / `tts<digits>` → `audio`; everything else → `text`.
  The long names match as substrings; the short ones (`sd`, `veo`, `tts`) match
  as whole tokens (the id split on non-alphanumerics), so an unrelated id is not
  mis-tagged.
- **L4 — Every CHAT model picker narrows the curated set to `text`.** The active
  connection's curated ids feeding `AgentModelCatalogueService.offered()` /
  `suggest()` — the web picker, the channel `/model` card, the turn-time note —
  and the Codex model catalogue Coffer projects into the agent's native config,
  all take the `text` entries and nothing else. An `embedding` / `image` /
  `video` / `audio` entry can never surface as a chat model. A connection that
  curates nothing still means no restriction, exactly as before.
- **Wire.** `ProviderOut.models`, `ProviderCreateRequest.models`,
  `ProviderPatchRequest.models` and `ProviderModelsOut.models` all become arrays
  of `{id, modality}` objects (a new `ProviderModel` component schema; `modality`
  is an enum defaulting to `text`). Empty still means unrestricted, and the patch
  semantics are unchanged: `null` leaves the set alone, `[]` clears the
  restriction.
- **L5 — The surface: the Models tab grows a TYPE column.** Each row of the
  connection detail page's Models table now reads model id · type · offered,
  where the type is a five-value Select pre-filled from what introspection
  guessed and corrected in place — the answer to "a provider should serve image,
  video and embedding models too" is that one column, not a second table. A
  correction on an already-offered row PATCHes the curated set immediately; one
  made on a row that is not offered yet is held on the surface and travels into
  the entry when its Switch is turned on. A Type filter sits beside the existing
  Offered filter. Downstream, every chat picker that reads the set — the agent
  Overview panel's model / fast-model dropdowns and the internal-engine card's
  model dropdown — offers `text` entries only, and treats a connection that
  curates SOMETHING but nothing `text` as offering no chat model rather than
  falling back to the endpoint's whole catalogue (what the daemon does).

**Refines:** J1/J2 (the curated set and the pickers that read it). **Unchanged:**
J3 — Coffer still writes down no model NAME and validates no id against a list of
its own; the modality is a kind, not a name.

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
- The retirement filter (the 2026-09-11b amendment): the agent's own catalogue
  minus the models the installed binary's own retirement table calls dead. The
  per-agent curated `models` set that amendment also introduced is WITHDRAWN —
  model curation lives on the channel now (channels FR-071), the field is gone
  and revision 0062 strips it from stored rows.
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
- `POST /api/v1/providers/{name}/rename` (`{new_name}`) → rename; moves the
  owned vault entry, repoints the audit trail and re-projects an active
  connection in one operation. 409 when another connection already holds the
  name, 404 when this one is absent, no-op when the name is unchanged
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
> preset** picker (OpenAI / Anthropic / Google Gemini / DeepSeek / OpenRouter /
> Ollama) that fills the endpoint + protocol, plus a **Custom**
> option that reveals a manual protocol selector for any other OpenAI-/Anthropic-
> compatible endpoint. The stored data model is unchanged (`protocol` is still a
> `ProviderConfig` field); only how it is chosen at create time changed. The
> `detect-protocol` probe endpoint stays for other callers but is no longer used
> by the form.

> **Amendment 2026-09-11 (the surface says what it manages).** The page stopped
> calling these things "LLM connections" — in the UI they are **model providers**,
> the name the sidebar and spec ui-shell already used. Four consequences for the
> surface, none of them touching the stored model or the API:
>
> - The list's second column and its filter are the **vendor** (OpenAI,
>   Anthropic, …), not the wire protocol. The vendor is DERIVED from `base_url`
>   by matching it against the preset list rather than stored — an endpoint that
>   matches no preset reads as Custom, which is also what happens if a user edits
>   a preset's base URL. The protocol stays visible on the detail page, where it
>   answers a question (how is this endpoint called) rather than sorting a list.
> - The **name** column keeps showing the user's own name for the provider: it is
>   the unique id the routes and CLI address, and renaming it to the vendor would
>   collapse two keys on the same vendor into one row.
> - The detail page splits its body into **Overview** and **Models** tabs, like
>   agent and MCP-server detail. The Models tab is a `DataTable` — one row per
>   model id with a per-row enable Switch, plus search and a status filter —
>   because a curated set of a real endpoint's models is a list, and every other
>   list in Coffer is that table. Empty selection still means NO RESTRICTION.
> - The **Moonshot (Kimi)** preset is gone.

> **Amendment 2026-09-11b (the surface, after the 2026-09-12 withdrawal).** The
> Agent page's Overview tab has no model control on the built-in login: the
> `AgentModelSelection` panel and the `GET|PUT …/models/selection` client that
> fed it are gone, and the branch renders one muted line saying the model is
> chosen per conversation — in the chat picker, with `/model <id>` in a channel,
> or by that channel's own default model. The non-built-in branch is untouched:
> a connection still binds its model / fast-model dropdowns. The catalogue
> endpoint stays, and the channel dialogs are what read it now
> ([channels](../channels/spec.md) FR-071).

> **Amendment 2026-09-12 (the surface, after A1–A3).** The edit dialog's Name
> field is editable and submits a rename ahead of the patch, with the detail
> page following the new URL (the route IS the name). The Models tab has no
> fetch button — it probes on open and offers a retry when that fails. The list
> row carries no internal-engine badge, and the detail header's read-only
> enabled/disabled badge is replaced by the shared `ScopeControl`.

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
still active and still compatible with that agent.

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

- **FR-025**: `ProviderConfig` MUST carry `models` — the set of model
  ids the connection OFFERS downstream (a `list[str]` as first written; **refined
  by FR-029** into a list of `{id, modality}` objects). An EMPTY list MUST mean no
  restriction
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

**Rename**

- **FR-027**: A connection MUST be renamable through a route of its own
  (`POST /api/v1/providers/{name}/rename`), NOT a `ProviderPatch` field. The
  operation MUST move, together: the resource row, the vault entry the
  connection owns (`provider/<name>/key` — unless another resource also cites
  that ref, in which case it MUST be left alone), the `audit_log` rows filed
  under `provider:<old>`, and — when the connection is active — the projection
  in every compatible agent's native config. It MUST record a `resource_renamed`
  audit event naming both names. A name another connection already holds MUST be
  refused with `RESOURCE_ALREADY_EXISTS` (409) BEFORE anything is written; an
  absent connection MUST be a 404; renaming to the current name MUST be a no-op.

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

### Key Entities

- **ProviderProfile**: A Resource of kind `provider`, identified by
  `provider:<name>`. Holds wire format, base URL, optional credential ref
  (absent for ollama), the curated `models` set it offers downstream (empty =
  unrestricted), per-wire `is_active` state, and the global `internal_default`
  flag. Never holds the raw secret, and never a chosen model.
- **`CuratedModel` / `Modality`**: One curated entry, `{id, modality}`, and the
  `StrEnum` over `text` / `embedding` / `image` / `video` / `audio` it carries
  (FR-029). The modality is Coffer's own note about an opaque id — stored, never
  re-derived at read time — and it is what narrows a connection's curated set to
  the chat models a picker may offer.
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
