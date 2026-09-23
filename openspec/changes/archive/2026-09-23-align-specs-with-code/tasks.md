## 1. Requirement text follows the code

- [x] 1.1 agent-registry: privileged-path list, config-file formats, secret-like header keys, unsupported-type message, model catalogue route and its citation
- [x] 1.2 skill-manager: fixed size cap, scope by agent uid in the delivery predicate and reconcile
- [x] 1.3 channels, channels/telegram, channels/seatalk: thread agent on `/new` and recreation, `channel_uid`, scope by uid, sticky agent stays local, rich-message card title, websocket `sdk_missing`, chunk sizes, inline media upload; Telegram Purpose caveat
- [x] 1.4 chat: partial output marked `complete` or `failed`, agent fixed after creation, archived controls, model picker options
- [x] 1.5 provider-switching: convergence by first name, unscoped default scope, Codex `developerInstructions`, curated `text` ids in the fixed list
- [x] 1.6 internal-engine and memory: curation owner in the settings row and synced document; memory's interval citation by title
- [x] 1.7 vault-sync: rollback leaves the pointer, pairings without the sticky agent, withheld tree paths, working tree over REST, key-match wording, scope by uid, curation pass naming
- [x] 1.8 mcp-gateway: exit 3 only when no daemon can be started, `first_seen_at` instead of an audit entry, `TOOL_DISABLED` for an out-of-scope call, preference documents keyed by uid
- [x] 1.9 daemon, desktop-app, credentials, resource-framework, web-ui: CLI residency commands, sanctioned host affordances, Purpose gaps, free-string audit actor, `engine` in the parity scenario, web-ui routes, filters, tabs and Settings descriptions

## 2. Shipped behaviour gets a requirement

- [x] 2.1 channels "Manage channels from the Channels page and the CLI": edit, rotate in place, test delivery, delete — test carries acceptance(channels, "rotating a channel secret keeps its refs and pairing")
- [x] 2.2 chat "Search the conversation list by title" — tests carry its three scenarios
- [x] 2.3 daemon "Change residency from the settings page or the command line" — tests carry both scenarios
- [x] 2.4 web-ui "Let the user choose when the daemon runs" — test carries acceptance(web-ui, "the general tab sets when the daemon runs")
- [x] 2.5 internal-engine "Report and change the curation owner from every surface" — tests carry both scenarios
- [x] 2.6 vault-sync "Fold consecutive quiet rounds into one row" — test carries acceptance(vault-sync, "repeated failures fold into one row and the newest round stands alone")
- [x] 2.7 channels/telegram "Render selection cards as inline keyboards" — test carries the rich-message heading scenario

## 3. Data models and contracts

- [x] 3.1 Correct every capability's `data-model.md` against the code (entities, fields, service methods, enums, migrations)
- [x] 3.2 Correct each `contracts/api.openapi.yaml`: status and error codes, enums, `required` response fields, descriptions
- [x] 3.3 Regenerate the frontend client (`npm run codegen`) and update test fixtures for newly required fields

## 4. Close

- [x] 4.1 Run `make verify`
- [x] 4.2 Archive the change (`npx openspec archive align-specs-with-code --yes`)
