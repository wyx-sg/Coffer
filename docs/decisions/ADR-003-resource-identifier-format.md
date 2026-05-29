# ADR-003: Resource Identifier Format — `<kind>:<name>`, Not URN

**Status**: Accepted
**Date**: 2026-05-20
**Deciders**: Yuxing Wu
**Related**: [ADR-001](ADR-001-resource-framework-upfront.md)

## Context

Resources need a stable, externally-visible identifier:

- The CLI shows it (`coffer resource show <id>`).
- The API uses it in URLs and request/response bodies.
- Future cross-resource references will hold it (e.g., an Agent's `tools` field
  listing the MCP servers it can use).
- The DB needs a primary key, but its on-disk form does not have to be the
  same as the external one.

Candidates considered:

- **Pure UUID** — globally unique, opaque.
- **Full URN per RFC 8141** — `urn:coffer:mcp_server:filesystem`.
- **`<kind>:<name>` colon-separated** — `mcp_server:filesystem`.
- **`<kind>/<name>` path-style** — `mcp_server/filesystem`.
- **Composite key without external string form** — `(kind, name)` only.

## Decision

External identifier is the string **`<kind>:<name>`**, with `kind` matching the
registered Resource kind and `name` user-chosen (kind-internally unique).

Database layout:

- Surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT` for joins and foreign keys.
- `UNIQUE (kind, name)` constraint enforces the external identifier's uniqueness.

A `ResourceRef(kind: str, name: str)` value object handles parsing and
serialisation at the domain boundary; raw strings never enter the domain.

## Consequences

**Positive**

- Short, human-readable. `mcp_server:filesystem` survives debugging without a
  decoder ring.
- Self-describing: the prefix says which kind to ask about, removing one query
  in many code paths.
- Maps cleanly to URLs: `/api/v1/resources/mcp_server/filesystem`.
- Maps cleanly to CLI: `coffer resource show mcp_server:filesystem`.
- Forward-compatible with URN if cross-instance config sharing ever matters —
  `urn:coffer:mcp_server:filesystem` is a strict superset, additive migration.

**Negative**

- The string form contains a colon, which is also a separator in many other
  contexts (URLs, env vars). Tooling that consumes resource refs must treat
  the _first_ colon as the kind/name separator and accept colons within names
  only if a future spec demands it (current convention: kebab-case names, no
  colons).
- "What is this string?" requires the reader to know coffer's convention.
  An IDE or doc must say "`<kind>:<name>`" near every reference.

## Alternatives Considered

**Full URN per RFC 8141** (`urn:coffer:mcp_server:filesystem`). Rejected. The
`urn:coffer:` prefix claims a namespace, but Coffer is single-user local-first
— there is no other Coffer to distinguish from. The 12-character overhead is
pure ceremony. If cross-instance sharing becomes a real concern, this ADR is
superseded by a new one switching to URN.

**Pure UUID** (`6ba7b810-9dad-11d1-80b4-00c04fd430c8`). Rejected. Not
human-readable; loses kind self-description; forces a separate `kind` field on
every reference.

**`<kind>/<name>` path-style**. Equivalent functionally and arguably URL-friendly,
but rejected because slashes are already overloaded (URL path separators, file
paths, identifiers in many DSLs). The colon makes the "kind-namespace + name"
relationship clearer at a glance, and matches conventions like `package:symbol`,
`gem:version`, `pip:dist`.

**Composite key, never serialised as one string**. Rejected. Cross-resource
references (Agent.config) need a single field to hold one reference; forcing
a `{kind, name}` object everywhere bloats configs and APIs for no benefit.
