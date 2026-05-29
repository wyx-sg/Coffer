# Coffer Roadmap

> Active specs only. We do not list specs that have not been committed to;
> roadmap entries reflect actual decisions, not aspirations. Future entries
> appear here when their spec is drafted, not before.

## Active

| #   | Spec                                                                          | Status                           |
| --- | ----------------------------------------------------------------------------- | -------------------------------- |
| 001 | **MCP Gateway** ([spec](../../specs/001-mcp-gateway/spec.md))                 | Accepted — code merged in PR #14 |
| 002 | **UI Shell & Visual Language** ([spec](../../specs/002-ui-shell/spec.md))     | Accepted — code merged in PR #23 |
| 003 | **MCP Gateway Desktop** ([spec](../../specs/003-mcp-gateway-desktop/spec.md)) | Accepted — code in review (PR #28) |

## Explicit non-goals (current spec)

Decisions about what `001-mcp-gateway` does **not** ship. Documented here so
reviewers do not mistake their absence for an oversight.

- **macOS Apple notarisation** — requires a paid Apple Developer account; users
  clear quarantine manually on first launch. Add when the account is set up.
- **Multi-machine sync** — the constitution forbids cloud system-of-record;
  revisit only via a constitutional amendment.
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

- [ADR-008: everything is a resource kind](../../docs/decisions/ADR-008-everything-is-a-resource-kind.md) — sidebar / IA architecture decision shared across all UI specs.

## How this file grows

When a new spec is drafted (`/speckit-specify` in Coffer's flow), add a row to
the **Active** table with its number, title, and status. When a spec ships,
update its status. Do **not** pre-allocate numbers or pre-name features that
have not yet had a spec written.
