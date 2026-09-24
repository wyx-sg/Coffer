# The Model Catalogue Is Read Back From the Installed Agent

**Status**: Accepted
**Date**: 2026-09-13
**Deciders**: Yuxing Wu
**Related**: [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Driving Agents Through the SDK and App Server](driving-agents-through-sdk-and-app-server.md), [Agent Descriptor Manifest](agent-descriptor-manifest.md), spec agent-registry "Read the model catalogue back from the installed agent", spec agent-registry "Keep one source of truth for an agent's models", spec agent-registry "Contribute models from the type's native config read-only", spec agent-registry "Carry reasoning-effort levels beside the model id", spec agent-registry "Read reasoning-effort levels from the agent runtime", spec provider-switching "Serve one model list to every surface", spec provider-switching "Curate the models a connection offers", PR #319, PR #352, PR #365, PR #378

## Context

Several surfaces let the owner choose which model an agent runs on: the web
Chat picker, a channel's `/model` and `/effort` cards, the agent detail page,
and the note an agent is told at turn time about which model it is on. They
must all offer the same list, or a model picked on the phone is missing on the
web.

The list changes on the agents' schedule, not Coffer's. Claude Code ships new
model tiers every few weeks; Codex's model set depends on the installed release
and the user's login. Neither CLI has a `list models` command.

What is locally knowable, and what is not:

- **Claude Code** is a single bun-compiled executable that embeds a model
  catalogue and an `aliases` table mapping each tier alias (`opus`, `sonnet`,
  `haiku`, `fable`) to the model it resolves to on a first-party account. The
  catalogue is cumulative and account-blind. On one install it listed nineteen
  models, of which the account could run nine, and no field separated the two
  groups. The CLI's own entitlement answer (`modelAccessCache` in
  `.claude.json`) is server-provided and routinely empty.
- **Codex** answers a `model/list` request over the same `codex app-server`
  JSON-RPC Coffer already uses to run turns. Per model, it reports
  `supportedReasoningEfforts` and `defaultReasoningEffort`.
- **Native config** holds local choices: Claude Code caches extra picker options
  in `.claude.json`; Codex profiles in `config.toml` name the model each one
  runs.
- **Reasoning effort** is a Codex turn parameter, not part of the model name.
  `thread/start` accepts an effort field and ignores it; the response keeps
  echoing the config default. `thread/settings/update` works but requires
  declaring the `experimentalApi` capability. `turn/start` honours it: the same
  prompt used 53 reasoning output tokens at `low` and 2569 at `xhigh`, measured
  from Codex's own token-usage notification.

When a Coffer connection is active for an agent, turns go to that endpoint,
not to the account the agent's catalogue describes.

## Options Considered

### Option A — Read the catalogue from the installed agent, per source, best-effort (chosen)

`AgentModelCatalogueService` (`application/agent/model_catalogue.py`) asks a
`ChainedModelDiscovery` wired in `surfaces/http/chat_wiring.py`, whose sources
answer in picker order:

1. `ClaudeBinaryModelDiscovery` (`infrastructure/agent/claude_binary_models.py`)
   locates the `aliases` table in the Claude Code binary and offers the four
   tier aliases, each labelled with the display name of the model it currently
   resolves to ("Opus 5"). Offering aliases, not versioned ids, matches what
   Claude Code's own picker offers, and an alias cannot fail on entitlement
   because the CLI resolves it against the account at turn time.
2. `CodexRpcModelDiscovery` (`infrastructure/agent/codex_rpc_models.py`) sends
   `model/list` to a short-lived `codex app-server`, with a timeout, and keeps
   each model's efforts and default effort.
3. `NativeConfigModelDiscovery` (`infrastructure/agent/model_discovery.py`)
   adds the models the CLIs have written into their own config files, read-only.

Each source degrades to an empty list on any failure — a missing CLI, a moved
bundle anchor, an unauthenticated or wedged Codex — and costs only its own
models. When a connection is active for the agent, `offered()` returns that
connection's curated `models` instead, while efforts still come from the
runtime. Nothing validates a model name: a name typed anywhere is passed to the
CLI verbatim. The effort rides beside the id — `AgentModel.efforts` and `.default_effort`
in the catalogue, `effort` beside `model` in the conversation's agent config
(`domain/chat/agent_config.py`) — and is sent on `turn/start`. An agent
that reports no efforts gets no effort control and no effort field.

Pros: a model released after Coffer shipped appears with no Coffer release; the
picker shows exactly what the agent itself would offer, with the version in the
label; every surface reads one service; a broken source cannot fail a request
or show a wrong model. Cons: the Claude source parses an undocumented bundle
layout that any release can move (it then returns nothing, and the picker falls
back to the other sources); the Codex source spawns a process per catalogue
read; a model that is not the current head of its family cannot be picked from
the list, only typed. It wins because it is the only option whose answer is
current by construction.

### Option B — A hardcoded model list in Coffer (the design replaced in PR #319)

Coffer ships a table of model ids per agent type.

Pros: fast, deterministic, no parsing of another program. Cons: the list went
stale the day a CLI shipped a new tier; it could not tell two releases of the
same tier apart, the one thing a picker has to show; and for Codex the names it
carried did not exist on the machine at all. A user whose new model never
appeared had no way to find out why. It lost on staleness.

### Option C — Ask the provider's `/models` endpoint

List models from the vendor or gateway API.

Pros: authoritative for what the endpoint serves. Cons: the agents' built-in
logins are OAuth sessions whose model APIs Coffer does not hold credentials
for; a gateway's `/models` lists dozens of models the agent's wire cannot use;
and it knows nothing about Claude Code's aliases or Codex's efforts. Coffer does
use the endpoint's catalogue where it is the right answer: when the owner
curates a connection's models, and when that connection is active for an agent.

### Option D — The user curates the list

Show the full versioned catalogue once; the user ticks which models to offer.

Pros: sidesteps entitlement, because the user knows what their account can run.
Cons: the curation needs an owner. It lived on the agent record, which
narrowed the list for every audience at once, then on each channel, which was
one more place to keep in step with a catalogue that changes by itself. Both
were removed (the agent field by migration 0063, the channel's by migration
0068). Aliases made curation unnecessary: the list is short and every entry
works.

### Option E — The full versioned catalogue, filtered by the CLI's retirement table

Read the embedded catalogue plus the bundle's retirement and remap table, and
apply the CLI's own "is this model gone" predicate.

Pros: offers specific versions; the filter used the CLI's own rule. Cons: the
catalogue still named models this account could not run, including whole
internal families, and there was no local way to tell them apart. The picker
filled with names that failed when picked. It was shipped briefly and replaced
by aliases (PR #378).

## Decision

Coffer holds no model table. Each agent type's catalogue is read from the
installed agent: Claude Code's tier aliases from its binary, Codex's models and
reasoning efforts from `model/list`, and local additions from both agents'
native config. The sources are composed in one service that every surface
reads. When a connection is active for the agent, its curated model set
replaces the agent's ids. Model names and effort levels are opaque and never
validated. Effort is a field beside the model, sent on each Codex turn.

## Consequences

- A new source or a new agent type adds a `ModelDiscoveryPort` implementation
  to the chain; the surfaces do not change.
- A Claude Code release that changes its bundle layout silently removes that
  source's models until the anchor is updated; the other sources still answer.
  A contract test for the Codex catalogue document
  (`backend/tests/integration/providers/test_codex_model_catalog.py`) guards the
  one place Coffer writes a model list for an agent to read.
- A model an account cannot run fails at the turn, with the agent's own error,
  not in the picker.
- The web picker, the channel cards and the turn-time model note cannot drift
  apart, because they share `offered()`.
