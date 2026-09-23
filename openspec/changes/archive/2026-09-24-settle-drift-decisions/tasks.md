## 1. Code

- [x] 1.1 Provider uid key route resolves no key for a disabled or unreached connection; CLI exits non-zero
- [x] 1.2 A second internal-engine default is refused (409) outside the dedicated route and dropped with a report when synced
- [x] 1.3 Knowledge: an oversized item is promoted as it stands or stamped, never left pending
- [x] 1.4 Chat: platform `stream_ended` backstop; partial output saved while streaming; shutdown stops turns before the database closes
- [x] 1.5 Telegram: no `getFile` for a file known to be over the cap
- [x] 1.6 `coffer agent models <agent_type> [--json]`
- [x] 1.7 `coffer sync remote set` keeps a paused remote paused; the web attention marker ignores a paused remote
- [x] 1.8 Desktop: `awaiting_join` is an attention status
- [x] 1.9 CLI: a daemon lost mid-command exits 3 with a message
- [x] 1.10 Gate `scripts/check_spec_citations.py` in `make lint`

## 2. Specs, data models, contracts

- [x] 2.1 Deltas for agent-registry, skill-manager, provider-switching, chat, channels, channels/telegram, knowledge, vault-sync, mcp-gateway, web-ui; Purpose edits for skill-manager and resource-framework
- [x] 2.2 Every new scenario's test carries its acceptance marker
- [x] 2.3 data-model and contract updates; regenerate the frontend client

## 3. Close

- [x] 3.1 Run `make verify`
- [x] 3.2 Archive the change
