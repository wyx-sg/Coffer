# Research — Provider Switching

Records the design alternatives considered, decisions reached, and rationale
for key choices. Corresponds to [Provider Switching](../../docs/decisions/provider-switching.md).

## Problem statement

Claude Code and Codex each read provider settings from separate native config
files in different formats (`~/.claude/settings.json` JSON;
`~/.codex/config.toml` TOML). Switching providers today means:

- Editing multiple files by hand.
- Storing raw API keys in plaintext in config files.
- Losing a unified audit trail.
- No cross-machine consistency (keys are machine-local).

## Decision A — one connection per account, activation per agent

### Options considered

**A1 (chosen): one connection = one account; at most one active per agent.**
A connection is a credentialed endpoint, and Claude Code and Codex share the
registry and may share a credential ref while being driven by separate
connection records.

*Rationale*: Simple, explicit, no implicit multi-agent fan-out that could
partially fail and leave inconsistent state. Each connection is independently
testable.

*What this later became*: A1 first tied a connection to ONE wire and made
activation per wire. Neither held. Which agents a connection drives is now the
resource's per-agent scope — that is how an OpenAI-compatible gateway is routed
to Claude Code — and the single-active invariant is per AGENT TYPE, because the
wire was never the thing being taken over. The model left the connection at the
same time, for the reason A2 gives below: the account and its uses are
different questions.

**A2: one record drives both agents simultaneously.**
A single record would inject into both `settings.json` and `config.toml`.

*Rejected*: Forces a many-fields-per-record design (claude_model, codex_model,
wire_api, fast_model all together). Unclear what "active" means when one agent
succeeds and the other fails. Violates the project's preference for minimal and
explicit semantics. The scope axis gets the useful half of A2 — one gateway
account reaching both agents — without collapsing two agents' state into one
flag.

**A3: per-agent provider with no shared registry.**
Each agent maintains its own provider list independently.

*Rejected*: Loses the governance benefit (unified audit, sync, encryption). This
is effectively the status quo.

## Decision B — credential isolation (key never plaintext in native config)

### Options considered

**B1 (chosen): apiKeyHelper for Claude Code; env_key for Codex.**
The raw key stays in the Fernet vault only. Claude Code reads the key via the
`apiKeyHelper` command-line hook — keyed by CONNECTION, so the agent always
reads the key of the connection that was activated rather than whatever the
wire resolves to. Codex reads the key from an env var.

*Rationale*: Consistent with the existing MCP `credential_refs` pattern. The
raw key never lands in any file on disk (other than the encrypted vault). Audit
log and sync workspace never contain plaintext secrets. `apiKeyHelper` is already
a native Claude Code feature designed for this purpose.

*Accepted consequence for Codex*: There is no equivalent of `apiKeyHelper` in
Codex; the closest mechanism is a named env var. Coffer writes
`env_key = "COFFER_PROVIDER_KEY"` into `config.toml` and materialises the key
into that variable for any Codex process it spawns itself; a Codex the user
starts in their own shell needs it exported there. This is documented in the
quickstart. The alternative (writing the raw key to `config.toml`) was rejected
as violating the credential-isolation principle.

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
periodically), switching the connection an agent is on takes effect on its next
request — the apiKeyHelper design makes hot-switch "nearly free" for Claude
Code. This is forward-looking only; hot-switch remains out of scope.

## Decision C — phased delivery; hot-switch is deferred

### Options considered

**C1 (chosen): registry + projection + switch + audit + convergence first;
hot-switch (mid-session reload) separately.**

*Rationale*: The projection step (a file write) is atomic and instant. Claude
Code gets effective hot-switching from `apiKeyHelper` with no extra work, and a
standalone Codex needs a manual env-var re-export, which is documented.
Deferring hot-switch keeps the foundation clean, auditable and well-tested.

**C2: hot-switch at the same time.**
Requires detecting running Claude Code / Codex processes, signalling them, and
handling partial failures. Substantially more complex.

*Rejected*: Violates the project's "minimal" principle. The foundation
(registry + projection) stands on its own and is valuable on its own.

## Native-config rationale

Which file is written is decided by the AGENT, not by the connection's wire; the
sections below are why each file's key set looks the way it does.

### Claude Code — `settings.json`

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

### Codex — `config.toml`

Codex's `~/.codex/config.toml` uses a named-provider model. Key choices:

- **`model_provider = "coffer"`**: Tells Codex to look up the `coffer` entry in
  `[model_providers]`.
- **`[model_providers.coffer]`**: Named provider block with `name`, `base_url`,
  `wire_api`, and `env_key`. Codex reads the key from `env_key` env var.
- **`wire_api`**: Was meant to switch between the Chat Completions API
  (`"chat"`) and the Responses API (`"responses"`). Codex dropped `chat` and now
  refuses to load a `config.toml` that names it, so `responses` is the only
  legal value and the setting is vestigial — it lives on the agent's binding,
  not on the connection.
- **`tomlkit`**: Used for merging to preserve comments and ordering in the file.
  String replacement was rejected (fragile and breaks user customisations).

## Why no proxy / failover / format conversion

- **No proxy**: Adding a local proxy service adds latency, a new component to
  manage, and requires clients to be reconfigured to hit the proxy. Out of scope.
- **No failover / fallback chains**: Activation is explicit and deterministic —
  one connection per agent type. Fallback chains would make the active
  connection ambiguous and harder to audit.
- **No format conversion**: Translating an Anthropic-shaped request into an
  OpenAI-shaped one (or the reverse) would require an intercepting proxy, which
  is explicitly a non-goal. Routing an OpenAI-compatible endpoint at Claude Code
  is supported — that is what the per-agent scope is for — but the endpoint must
  really speak what the agent sends; Coffer only decides which file gets written,
  never what goes over the wire.

## Sync and audit design

**Sync**: Modeling `provider` as a ResourceService Kind is the minimal path to
convergence. The exporter serialises every kind into the working tree and the
resource applier puts the merged difference back, both automatically; adding
`provider` costs one Kind registration in the composition root. No new table is
needed, because the `resources` table already handles arbitrary kinds via its
`kind` column. What the kind had to add for itself is the post-import hook that
re-derives each agent's projection, since writing a native config file is a
machine-local side effect no document can carry.

Credential sync: credentials already sync as Fernet ciphertext (not plaintext)
at `credentials/<ref>.enc`. The master key never leaves a machine. This is the
same pattern used by MCP server credentials (spec credentials).

**Audit**: `RESOURCE_CREATED`, `RESOURCE_UPDATED`, `RESOURCE_DELETED` are
emitted automatically by `ResourceService`. Adding `PROVIDER_SWITCHED` as a
separate, dedicated event (rather than reusing a generic switch event) is
intentional: it carries structured details (`{from, to, protocol, agents}`)
that enable auditors to reconstruct the full switch history without scanning
resource-update diffs.

## Alternatives considered but not in this spec

- **Provider drift-verify**: Continuously checking whether the live
  `settings.json` / `config.toml` matches the active connection. Deferred. The
  narrow version that did ship is the boot self-check, which clears `is_active`
  when the projection is no longer in the file — drift happens whenever anything
  else rewrites a config Coffer does not own.
- **Auto env-injection into a Codex the USER starts**: Coffer materialises
  `COFFER_PROVIDER_KEY` for the Codex processes it spawns itself, but it cannot
  reach a shell the user opened. Writing to a shell init file on the user's
  behalf was rejected; the quickstart documents the one-line export instead.
- **Full native-config restore**: returning a config file to its exact
  pre-Coffer state. Reverting to an agent's built-in login DID ship
  (`use-builtin/{wire}` removes the keys Coffer owns), but a general restore is
  deferred: the `.bak` copies provide manual recovery, and the semantics are
  unclear once the user has made their own edits after a switch.
