## MODIFIED Requirements

### Requirement: Project into Claude Code settings without clobbering them
The system MUST project into the agent's `<config_dir>/settings.json` (`~/.claude/settings.json`
for the default config directory) through
[agent-registry](../agent-registry/spec.md)'s config-write machinery — the atomic write with its
timestamped backup and the fingerprint that refuses a write onto content that
changed underneath it ([agent-registry](../agent-registry/spec.md) "Back up and compare-and-swap every write Coffer makes to an agent's config") — merging only the managed keys and preserving
everything else. Coffer MERGES into the user's existing file and never replaces it; a file that does
not exist is created with only the managed keys, and switching an agent onto a connection MUST NOT touch any key
outside the managed set. The managed key set per agent and the ownership markers that make
de-projection safe are in [data-model.md](data-model.md).

No provider key reaches Claude Code at all: `env.ANTHROPIC_BASE_URL` is the local model proxy's
Anthropic route, `http://127.0.0.1:<proxy port>/anthropic`, and the agent authenticates to the proxy
with its own local token (see "Authenticate each agent to the proxy with its own local token"),
which the proxy exchanges for the connection's key upstream. `ANTHROPIC_API_KEY` MUST NOT be
written. Claude Code gets
`apiKeyHelper = "<absolute path to the coffer CLI> proxy token --agent-uid <agent uid>"`, which it
invokes to fetch that token (and re-invokes periodically); the path is absolute because Claude Code
runs the helper with its own `PATH`. `env.NO_PROXY` gains `127.0.0.1,localhost`, appended to the
user's own entries, so a corporate `HTTPS_PROXY` never captures the loopback leg; de-projection
takes back only that appended pair. Because the file names the proxy rather than the connection,
switching the agent from one API-key connection to another changes the proxy's route and leaves
`settings.json` as it is.
The model keys Coffer writes for Claude Code are these and no others (see "Take projected model keys
from the agent's binding"): the top-level `model` key for the agent's model — never
`env.ANTHROPIC_MODEL`, which outranks `model` and would undo the user's own `/model` choice at every
launch; `env.ANTHROPIC_DEFAULT_OPUS_MODEL`,
`env.ANTHROPIC_DEFAULT_SONNET_MODEL`, `env.ANTHROPIC_DEFAULT_HAIKU_MODEL` and, when a Fable tier is
pinned, `env.ANTHROPIC_DEFAULT_FABLE_MODEL`, from "Suggest a model for each Claude Code tier"; and
`modelPicker`, which fills Claude Code's `/model` picker with the connection's curated text models,
replacing the built-in rows on an endpoint that serves no Claude ids and keeping them on one that
does. Every option Coffer writes into `modelPicker` carries the description `via Coffer`, which is
how de-projection tells Coffer's picker from the user's. For a connection to
a model runtime on this machine it also writes `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` (local
runtimes reject Claude Code's beta request fields) and `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` set to
the chosen model's recorded window (Claude Code otherwise assumes 200k for an id it does not know).

Coffer writes no reasoning-effort key: an `effortLevel` already in the file is the user's own and is left as it is.

De-projection drops `apiKeyHelper` only when it is Coffer's own — a helper line running the coffer
CLI (by absolute path or bare) with `proxy token` — and leaves a helper the user wrote alone.

Every projection write — this one, the Codex one (see "Project into Codex config without overwriting it"), and their de-projections — MUST surface a fingerprint refusal as 409 `CONFIG_FILE_STALE` and
MUST audit it as `provider_projection_refused`, so a concurrent edit by the user or by the agent's
own CLI is never silently overwritten.

#### Scenario: activate an anthropic profile writes Claude Code settings
- **GIVEN** a Claude Code agent is registered and a connection reaching it exists,
- **WHEN** the user switches the Claude Code agent onto the connection,
- **THEN** `~/.claude/settings.json` contains `apiKeyHelper` printing that agent's proxy token and `env.ANTHROPIC_BASE_URL` naming the proxy's loopback Anthropic route; neither the connection's endpoint nor its key appears in the file, `ANTHROPIC_API_KEY` is absent; and the agent's `connection_uid` becomes the connection's uid.
#### Scenario: switching preserves unrelated native-config keys and writes a .bak backup
- **GIVEN** `~/.claude/settings.json` contains keys Coffer does not manage (e.g. `theme`, `mcpServers`),
- **WHEN** the user switches that agent onto a connection reaching it,
- **THEN** those keys are preserved byte-for-byte in the updated file, a timestamped copy of the prior file is written under `~/.coffer/config-backups/` before the update, and nothing is written next to it, and only the Coffer-managed keys are changed.
#### Scenario: projection refuses to overwrite a concurrent edit
- **GIVEN** `~/.claude/settings.json` that the user saves from their editor after Coffer has read it and before Coffer writes its projection,
- **WHEN** the projection write runs,
- **THEN** the write is refused with 409 `CONFIG_FILE_STALE`, the user's edit is left intact on disk, no backup is written, and an audit row `provider_projection_refused` names the connection, the agent type and the file — the caller re-reads and retries.

