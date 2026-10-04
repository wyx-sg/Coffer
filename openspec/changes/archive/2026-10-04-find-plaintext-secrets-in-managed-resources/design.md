## Context

The removed scan (`b6cddd34b^`: `plaintext_scan.scan/move`, `ScanSecretsDialog`)
handled skill files and a legacy folder. MCP servers keep their secrets as
refs in `transport.secret_refs` (`{env var or header name: ref}`); the static
`env`/`headers` maps refuse only a few token prefixes, so `DB_PASSWORD=hunter2…`
or `X-Api-Key: …` slips through. Custom tools are `mcp_server` rows with an
`http_api` transport, with the same `headers`/`secret_refs` pair.

## Decisions

- **Two sources, one scan.** Skills are files, scanned with the existing
  `find_in_text` rules; servers are configs, scanned by key name and value
  shape. One finding list, a `source` field to group by.
- **A server's value stays the server's.** It becomes a resource-owned ref
  (`mcp_server/<uuid4 hex>/<key>`, the shape the UI mints), not a standalone
  secret: the server is its only consumer, and the Secrets page already lists
  such refs under the server. The config change goes through
  `ResourceService.update_config`, so validation, audit, reconcile and the
  secret boundary's binding all run; a fresh ref written moments ago for a
  just-changed destination is approved without a person.
- **Store first, then rewrite.** As before: the file or config changes only
  once the store reads the value back. A server whose config update fails
  deletes the ref it just wrote, so nothing is left half-moved.
- **Finding ids** are a hash of the location (source, resource uid or file,
  line or field, key), so a dry run and the import that follows agree, and a
  finding that moved does not come back.
- **Coffer's own bundled skills** are skipped, as before.

## Risks

- A false positive moves a non-secret value into the store. The dialog shows
  every finding ticked but reviewable, the dry run lists each change, and the
  value still reaches its consumer unchanged, just encrypted.
