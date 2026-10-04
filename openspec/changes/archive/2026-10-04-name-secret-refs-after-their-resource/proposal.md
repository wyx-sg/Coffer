## Why

A resource's secret is minted at `<kind>/<uuid4 hex>/<slot>` — the Secrets
page's Copy reference, the Used by note, `coffer secret list` and the vault's
`secret/` folder all show `mcp_server/643784232a6652abbf02c0f6aaf4a904/CONFLUENCE_PERSONAL_TOKEN`
or `provider/9c…/key`, and older vaults hold earlier shapes still
(`postman.AUTHORIZATION`, `agnes-apihub`). Nobody can tell from a ref whose
secret it is. The ref was kept free of the name so a rename would not move a
secret; but MCP server names are now fixed, and the two kinds that rename
(channel, provider) can move their refs with them.

## What Changes

- A resource's own secret is named `<kind>/<resource name>/<slot>`:
  `mcp_server/confluence/CONFLUENCE_PERSONAL_TOKEN`, `channel/seatalk/app-secret`,
  `provider/agnes/key`. Every place that mints one — the MCP server and channel
  dialogs, provider creation, the plaintext import — mints that.
- Renaming a channel or provider moves the refs named after it to the new name.
- At daemon start, every ref that exactly one resource cites in exactly one
  slot, and that is not already named that way, is moved to its name — value,
  citing config, and this machine's approval, creation-time and last-used
  records together. A ref shared by several citers, and every standalone
  `secret/<name>`, keeps its name.
- Each move is audited as `secret_renamed` (from, to), never with a value.

## Impact

- Backend: `domain/secrets.py` (the naming rule), a ref-move service in
  `application/secret/`, `application/provider/service.py`, the channel and
  provider rename hooks, daemon startup wiring, `plaintext_move.py`,
  `domain/audit.py`.
- Frontend: `lib/secretRef.ts` and its callers (channel schema, MCP edit save).
- Specs: secret. ADR: a new one for ref naming; credential-references updated.
- Docs: guides/secret-store, guides/secrets (en + zh).
