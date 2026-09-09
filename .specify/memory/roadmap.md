# Coffer Roadmap

> Active specs only. We do not list specs that have not been committed to;
> roadmap entries reflect actual decisions, not aspirations. Future entries
> appear here when their spec is drafted, not before.

## Active

| #   | Spec                                                                          | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 001 | **MCP Gateway** ([spec](../../specs/001-mcp-gateway/spec.md))                 | Accepted — code merged in PR #14; amended with `coffer__search_tools` tool-retrieval for aggregation overload ([ADR-018](../../docs/decisions/ADR-018-tool-retrieval-for-overload.md)) · `coffer__search_tools` gains semantic (embedding) ranking with BM25 fallback ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) amends ADR-018) · **Desktop shell retired (2026-09-09):** spec 003 (MCP Gateway Desktop) is retired and its directory deleted; the daemon now serves the built web UI itself at its own loopback origin, `coffer open` mints a single-use short-lived code to hand the browser an authenticated session, the frozen daemon deploys its sibling binaries into `~/.coffer/bin/` on start, and the release collapses to one `coffer-cli-<triple>.tar.gz` tier plus an aggregated `SHA256SUMS` (spec 001 FR-022–FR-026, [ADR-008](../../docs/decisions/ADR-008-distribution-pyinstaller.md)) |
| 002 | **UI Shell & Visual Language** ([spec](../../specs/002-ui-shell/spec.md))     | Accepted — code merged in PR #23                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 004 | **Agent Registry** ([spec](../../specs/004-agent-registry/spec.md))           | Accepted — code merged · **Repositioned:** the `builtin` agent is retired as a registered chat agent and recast as an internal Coffer capability; the registry lists managed agents only ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)) · **Narrowed to two types:** the registry supports `claude_code` and `codex` only. `opencode`, `hermes`, `cursor` and `openclaw` are removed — none was installed on the maintainer's machine, so their facets were written against docs and one-off probes and could never be regression-tested locally. Their removal collapses the three context-injection mechanisms back to one shell hook and retires the per-facet capability matrix (spec 004 FR-003a) |
| 005 | **Skill Manager** ([spec](../../specs/005-skill-manager/spec.md))             | Accepted — code merged                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| 006 | **Knowledge Base** ([spec](../../specs/006-knowledge-base/spec.md))           | Accepted — code merged in PR #55 (KB face of the knowledge substrate, [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md))                                                                                                                                                                                                                                                                                                                                                                                                              |
| 007 | **Memory** ([spec](../../specs/007-memory/spec.md))                           | Accepted — code merged in PRs #55/#58 (shared agent-native memory, [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) + [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)) · **Removed 2026-09-09:** transcript distillation (the automatic ingest half of the memory loop) and the `journal` lane it wrote into; writes are explicit — `coffer__remember` in, `coffer__recall` out, over the `knowledge` / `rules` / `handoff` lanes · **Amendment 2026-07-10:** AI-assisted merge of same-project stores — internal-engine judgment + additive consolidation + no-resurrection identity aliases ([amendment](../../specs/007-memory/amendment-2026-07-10-ai-store-merge.md)) |
| 008 | **Agent Chat** ([spec](../../specs/008-agent-chat/spec.md))                   | Accepted — code merged in PR #57 · **Repositioned:** Agent Chat → Vault Console (talk to the vault + observe/approve channel-driven turns); de-scopes in-browser daily coding chat ([ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.md)) · **Re-repositioned:** the built-in agent is retired as a chat persona; chat talks to managed agents only and the surface reverts to "Chat", while the channel observe/approve job stands ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) partially supersedes ADR-021) |
| 009 | **Channels** ([spec](../../specs/009-channels/spec.md))                       | Accepted — code merged in PR #59 ([ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md))                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 010 | **Vault Export & Import** ([spec](../../specs/010-sync/spec.md))              | Accepted — **downgraded from continuous multi-machine sync.** Coffer now exports the vault to a directory the user picks and imports one back; no remote, no git workspace, no background worker, no machine registry and no tombstones ([ADR-016](../../docs/decisions/ADR-016-vault-export-import.md)). Carrying the directory between machines is the user's business, so the feature needs no exception to Principle I — the constitution 0.4.0 amendment removes the 0.3.0 user-controlled-medium exception · **Scope collapsed to one axis:** resource `scope` is a list of agent names, not a machine × agent matrix; the top-level Machines fleet view is removed along with the machine identities it rendered ([ADR-045](../../docs/decisions/ADR-045-per-agent-resource-scope.md)) |
| 011 | **Provider Switching** ([spec](../../specs/011-provider-switching/spec.md))   | Draft — shared provider profile registry; project once, switch atomically into Claude Code / Codex native config; credential isolation via apiKeyHelper / env_key; Fernet vault + full audit + sync ([ADR-032](../../docs/decisions/ADR-032-provider-switching.md))                                                                                                                                                                                                                                                                                             |

## Explicit non-goals (current spec)

Decisions about what `001-mcp-gateway` does **not** ship. Documented here so
reviewers do not mistake their absence for an oversight.

- **macOS Apple notarisation** — requires a paid Apple Developer account; users
  clear quarantine manually on the extracted release binaries. Add when the
  account is set up.
- **A desktop shell** — retired 2026-09-09. Every desktop update cost a rebuild
  plus a reinstall, and the built artifact kept drifting from source; the
  daemon-served web UI needs only a daemon restart and a hard refresh.
- **Streaming progress forwarding through the gateway** — no mainstream MCP
  gateway does this; this spec matches the ecosystem (token passthrough +
  timeout reset, no active forward).
- **System service install** (launchd / systemd / Windows service) — additive
  to [ADR-006](../../docs/decisions/ADR-006-daemon-detect-or-spawn.md)'s detect-or-spawn pattern; can be added later as
  `coffer daemon install --system` without breaking the current model.
- **Plugin marketplace / third-party kind authoring** — see [ADR-001 / ADR-002
  alternatives](../../docs/decisions/ADR-001-resource-framework-upfront.md).
- **Tool call argument or result persistence** — the invocation log records
  who / when / how-long / outcome only; argument and result content are
  considered sensitive and stay out of the database.

## Cross-cutting decisions

- [ADR-007: everything is a resource kind](../../docs/decisions/ADR-007-everything-is-a-resource-kind.md) — sidebar / IA architecture decision shared across all UI specs.
- [ADR-018: tool retrieval for aggregation overload](../../docs/decisions/ADR-018-tool-retrieval-for-overload.md) — the `coffer__search_tools` retrieval primitive that amends spec 001.
- [ADR-024: the built-in agent is an internal capability, not a chat persona](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) — retires the built-in chat persona (chat = managed agents only); recasts the local model as an internal capability: semantic `coffer__search_tools` (amends ADR-018).

## How this file grows

When a new spec is drafted (`/speckit-specify` in Coffer's flow), add a row to
the **Active** table with its number, title, and status. When a spec ships,
update its status. Do **not** pre-allocate numbers or pre-name features that
have not yet had a spec written.
