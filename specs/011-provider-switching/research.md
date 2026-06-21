# Research — 011 Provider Switching

Records the design alternatives considered, decisions reached, and rationale
for key choices. Corresponds to ADR-032.

## Problem statement

Claude Code and Codex each read provider settings from separate native config
files in different formats (`~/.claude/settings.json` JSON;
`~/.codex/config.toml` TOML). Switching providers today means:

- Editing multiple files by hand.
- Storing raw API keys in plaintext in config files.
- Losing a unified audit trail.
- No cross-machine consistency (keys are machine-local).

## Decision A — single-wire profile, per-agent activation

### Options considered

**A1 (chosen): one profile = one wire format; at most one active per wire.**
A profile knows its wire format and projects to at most one native agent.
Claude Code and Codex share the registry and can share a credential ref, but
are driven by separate profile records.

*Rationale*: Simple, explicit, consistent with the existing single-active
pattern in `ModelConfig.is_default`. No implicit multi-agent fan-out that could
partially fail and leave inconsistent state. Each profile is independently
testable.

**A2: one profile drives both agents simultaneously.**
A single profile would inject into both `settings.json` and `config.toml`.

*Rejected*: Forces a many-fields-per-profile design (claude_model,
codex_model, wire_api, fast_model all together). Unclear what "active" means
when one wire succeeds and the other fails. Violates the project's preference
for minimal and explicit semantics.

**A3: per-agent provider with no shared registry.**
Each agent maintains its own provider list independently.

*Rejected*: Loses the governance benefit (unified audit, sync, encryption). This
is effectively the status quo.

## Decision B — credential isolation (key never plaintext in native config)

### Options considered

**B1 (chosen): apiKeyHelper for Claude Code; env_key for Codex.**
The raw key stays in the Fernet vault only. Claude Code reads the key via the
`apiKeyHelper` command-line hook. Codex reads the key from an env var.

*Rationale*: Consistent with the existing MCP `credential_refs` pattern. The
raw key never lands in any file on disk (other than the encrypted vault). Audit
log and sync workspace never contain plaintext secrets. `apiKeyHelper` is already
a native Claude Code feature designed for this purpose.

*Accepted consequence for Codex*: There is no equivalent of `apiKeyHelper` in
Codex; the closest mechanism is a named env var. Coffer writes
`env_key = "COFFER_PROVIDER_KEY"` into `config.toml`, and the user must export
that env var before starting Codex. This is documented in the quickstart. The
alternative (writing the raw key to `config.toml`) was rejected as violating the
credential-isolation principle.

**B2: write the raw key to native config files.**
Write `ANTHROPIC_API_KEY` to `settings.json` and `api_key` to `config.toml`.

*Rejected*: Contradicts the project's "credential isolation" principle (MEMORY
notes: "MCP credential_refs pattern"). Plaintext keys in config files are
exposed to sync, backup, and git history. Inconsistent with how MCP servers
are managed.

**B3: Coffer acts as a local proxy (key never leaves Coffer process).**
Coffer exposes a local endpoint; `apiKeyHelper` hits the proxy, which injects
the key and forwards the request.

*Rejected*: Out of scope per confirmed design. Explicitly listed as a non-goal
(no proxying / format conversion). Adds latency, complexity, and a new
infrastructure dependency.

### Forward-looking note on hot-switch

Because Claude Code re-invokes `apiKeyHelper` before each request (or
periodically), switching the active anthropic profile in Coffer immediately
affects the next Claude Code request — the apiKeyHelper design makes hot-switch
"nearly free" for Claude Code. This is noted as forward-looking only; hot-switch
is explicitly out of scope for this PR.

## Decision C — phased delivery; hot-switch is deferred

### Options considered

**C1 (chosen): ship registry + projection + switch + audit + sync in this PR;
hot-switch (mid-session reload) in a later PR.**

*Rationale*: The projection step (file write) is already atomic and instant.
Claude Code users get effective hot-switching via `apiKeyHelper` without any
additional work. Codex users need a manual env-var re-export, which is
documented. Deferring hot-switch lets this PR ship a clean, auditable,
well-tested foundation.

**C2: ship hot-switch in this PR.**
Requires detecting running Claude Code / Codex processes, signalling them, and
handling partial failures. Substantially more complex.

*Rejected*: Violates the project's "minimal" principle. The foundation
(registry + projection) can ship independently and is valuable on its own.

## Wire-format rationale

### anthropic wire → Claude Code

Claude Code's `~/.claude/settings.json` is the canonical settings file. Key
choices:

- **`apiKeyHelper`**: Native Claude Code feature; the helper command is invoked
  to fetch the key. This is the recommended way to avoid storing keys in
  `settings.json`.
- **`env.*` keys**: Claude Code reads these from the `env` section and exports
  them before starting its underlying SDK process. Managed keys are
  `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`.
- **Never `ANTHROPIC_API_KEY`**: Writing this key would override `apiKeyHelper`
  and expose the key in the file.
- **Merge, not replace**: Coffer only touches the defined managed keys.
  Everything else (theme, `mcpServers`, `permissions`, …) is preserved.

### openai wire → Codex

Codex's `~/.codex/config.toml` uses a named-provider model. Key choices:

- **`model_provider = "coffer"`**: Tells Codex to look up the `coffer` entry in
  `[model_providers]`.
- **`[model_providers.coffer]`**: Named provider block with `name`, `base_url`,
  `wire_api`, and `env_key`. Codex reads the key from `env_key` env var.
- **`wire_api`**: Allows switching between the Chat Completions API (`"chat"`)
  and the Responses API (`"responses"`) as Codex's native protocol.
- **`tomlkit`**: Used for merging to preserve comments and ordering in the file.
  String replacement was rejected (fragile and breaks user customisations).

## Why no proxy / failover / format conversion

- **No proxy**: Adding a local proxy service adds latency, a new component to
  manage, and requires clients to be reconfigured to hit the proxy. Out of scope.
- **No failover / fallback chains**: Per-profile activation is explicit and
  deterministic. Adding fallback chains would make the active provider ambiguous
  and harder to audit.
- **No format conversion**: A profile whose `wire_format` is `anthropic` speaks
  the Anthropic API natively. Translating it to an OpenAI-shaped request (or
  vice versa) would require an intercepting proxy, which is explicitly a
  non-goal. If a user wants to use an OpenAI-compatible endpoint with Claude
  Code, they should create an `openai` profile and a Codex agent, not ask Coffer
  to translate on the fly.

## Sync and audit design

**Sync**: Modeling `provider` as a ResourceService Kind is the minimal path to
sync support. `SyncExporter` and `SyncImporter` handle all kinds automatically;
adding `provider` costs one Kind registration in the composition root and a
`wire_provider_kind` helper. No new migration is needed because the `resources`
table already handles arbitrary kinds via the `kind` column.

Credential sync: credentials already sync as Fernet ciphertext (not plaintext)
at `credentials/<ref>.enc`. The master key never leaves a machine. This is the
same pattern used by MCP server credentials (spec 001).

**Audit**: `RESOURCE_CREATED`, `RESOURCE_UPDATED`, `RESOURCE_DELETED` are
emitted automatically by `ResourceService`. Adding `PROVIDER_SWITCHED` as a
separate, dedicated event (rather than reusing a generic switch event) is
intentional: it carries structured details (`{from, to, wire_format, agents}`)
that enable auditors to reconstruct the full switch history without scanning
resource-update diffs.

## Alternatives considered but not in this spec

- **Provider drift-verify**: Checking whether the live `settings.json` /
  `config.toml` matches the active profile. Deferred to spec 4.9. Not
  implemented here because the projection step itself is authoritative; drift
  can only happen if the user edits config files by hand after a switch.
- **Auto env-injection into Coffer-spawned Codex**: Would require Coffer's
  process spawning to read the active openai profile and inject
  `COFFER_PROVIDER_KEY`. Deferred with hot-switch.
- **Explicit deactivate / native-config restore**: "Undo" a switch by restoring
  config to a pre-Coffer state. The `.bak` backup provides manual recovery.
  Automated restore is deferred (complexity, unclear semantics when users make
  additional edits after a switch).
