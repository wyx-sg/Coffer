## 1. Backend

- [x] 1.1 File the channel kind under `local/` (storage class `local`)
- [x] 1.2 Remove `runs_on` from the channel config, the runtime gate, the kind's validators and the status
- [x] 1.3 Keep pairings in `local/channel-peers.json`; drop the `channel-peers` state area
- [x] 1.4 One-time migration of vault channels and pairings to `local/`

## 2. Frontend

- [x] 2.1 Remove the machine binding from the Channels page (Runs on, Elsewhere, unbound, Run it here)

## 3. Docs

- [x] 3.1 ADR channels-are-machine-local-resources; rewrite the ADRs that described synced channels
- [x] 3.2 docs-site (en + zh): vault sync, resource framework, chat, channel guides, glossary
