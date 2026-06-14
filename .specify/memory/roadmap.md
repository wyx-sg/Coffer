# Coffer Roadmap

> Active specs only. We do not list specs that have not been committed to;
> roadmap entries reflect actual decisions, not aspirations. Future entries
> appear here when their spec is drafted, not before.

## Active

| #   | Spec                                                                          | Status                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 001 | **MCP Gateway** ([spec](../../specs/001-mcp-gateway/spec.md))                 | Accepted — code merged in PR #14; amended with `coffer__search_tools` tool-retrieval for aggregation overload ([ADR-018](../../docs/decisions/ADR-018-tool-retrieval-for-overload.md))                                                                                                                                                                                                                                                               |
| 002 | **UI Shell & Visual Language** ([spec](../../specs/002-ui-shell/spec.md))     | Accepted — code merged in PR #23                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 003 | **MCP Gateway Desktop** ([spec](../../specs/003-mcp-gateway-desktop/spec.md)) | Accepted — code merged in PR #28                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 004 | **Agent Registry** ([spec](../../specs/004-agent-registry/spec.md))           | Accepted — code merged                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 005 | **Skill Manager** ([spec](../../specs/005-skill-manager/spec.md))             | Accepted — code merged                                                                                                                                                                                                                                                                                                                                                                                                                               |
| 006 | **Knowledge Base** ([spec](../../specs/006-knowledge-base/spec.md))           | Accepted — code merged in PR #55 (KB face of the knowledge substrate, [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md))                                                                                                                                                                                                                                                                                                    |
| 007 | **Memory** ([spec](../../specs/007-memory/spec.md))                           | Accepted — code merged in PRs #55/#58 (shared agent-native memory, [ADR-012](../../docs/decisions/ADR-012-files-as-truth-sqlite-retrieval.md) + [ADR-013](../../docs/decisions/ADR-013-agent-native-shared-memory.md)) · **Extension in progress:** transcript distillation — read-only ingest of local agent transcripts → LLM distillation → memory facts; no new spec number ([ADR-020](../../docs/decisions/ADR-020-transcript-distillation.md)) |
| 008 | **Agent Chat** ([spec](../../specs/008-agent-chat/spec.md))                   | Accepted — code merged in PR #57 · **Repositioned:** Agent Chat → Vault Console (talk to the vault + observe/approve channel-driven turns); de-scopes in-browser daily coding chat ([ADR-021](../../docs/decisions/ADR-021-chat-as-vault-console.md))                                                                                                                                                                                                |
| 009 | **Channels** ([spec](../../specs/009-channels/spec.md))                       | Accepted — code merged in PR #59 ([ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md))                                                                                                                                                                                                                                                                                                                                              |
| 010 | **Multi-Machine Sync** ([spec](../../specs/010-sync/spec.md))                 | Accepted — sync vault state over the user's own git repo ([ADR-016](../../docs/decisions/ADR-016-multi-machine-sync.md)); enabled by the constitution 0.3.0 amendment to Principle I                                                                                                                                                                                                                                                                 |

## Explicit non-goals (current spec)

Decisions about what `001-mcp-gateway` does **not** ship. Documented here so
reviewers do not mistake their absence for an oversight.

- **macOS Apple notarisation** — requires a paid Apple Developer account; users
  clear quarantine manually on first launch. Add when the account is set up.
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

## How this file grows

When a new spec is drafted (`/speckit-specify` in Coffer's flow), add a row to
the **Active** table with its number, title, and status. When a spec ships,
update its status. Do **not** pre-allocate numbers or pre-name features that
have not yet had a spec written.
