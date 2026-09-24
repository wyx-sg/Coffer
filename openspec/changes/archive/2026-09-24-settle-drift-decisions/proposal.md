## Why

The drift audit left a set of questions where either side could be right. The
owner settled each one. Some decisions change the code, some change the spec,
and several need both; this change records every one of them as requirement
text with a tested scenario.

## What Changes

- agent-registry: agents carry the kind-agnostic `enabled` flag, and disabling one
  reclaims its skills, stops memory reads and drops it from the catalogue;
  `coffer agent models <agent_type>`; config writes may carry a fingerprint and
  `config edit` always does; a vanished native-memory store reads as an empty tree;
  PATCH leaves an omitted model binding unchanged.
- skill-manager: the file viewer and editor are REST and web only; adopting from a
  disabled agent links the skill in place.
- provider-switching: a disabled or unreached connection's uid helper resolves no
  key; a second internal-engine default is refused on every write path and
  dropped, not fatal, when it arrives by sync; Codex keeps its own list for a
  connection that curates no text model.
- chat: the platform reports a stream that ends without a terminal event; partial
  output is saved while streaming and kept, marked failed, across a crash or a
  shutdown; `conversations.owner` is documented.
- channels: an oversized Telegram file is noted once and never requested; unknown
  config keys are ignored.
- knowledge: every curation outcome is a 200 status; an oversized item is kept as
  it stands.
- vault-sync: `awaiting_join` asks for a human on every surface; a paused remote
  runs nothing, asks nothing and stays paused when reconfigured.
- mcp-gateway: a daemon lost mid-command exits 3 with a message.
- web-ui and resource-framework: the shared-table rule covers Sync's Runs tab; the
  in-flight passes read records why it has no CLI.
- A gate checks that every cited requirement title exists and that retired id
  forms do not return.

## Capabilities

### New Capabilities

### Modified Capabilities

- `agent-registry`
- `skill-manager`
- `provider-switching`
- `chat`
- `channels`, `channels/telegram`
- `knowledge`
- `vault-sync`
- `mcp-gateway`
- `web-ui`
- `resource-framework`

## Impact

Backend (providers, knowledge curation, chat turns and shutdown, sync apply and
CLI, agent CLI, Telegram media), the web sync attention marker, the desktop
attention list, contracts for agent-registry, provider-switching, knowledge,
vault-sync and chat with a regenerated client, and a new lint gate
`scripts/check_spec_citations.py`.
