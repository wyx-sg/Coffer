## 1. Backend

- [x] 1.1 Health vocabulary and classification (`domain/provider/health.py`)
- [x] 1.2 `provider_health` table and repo in `derived.db`
- [x] 1.3 Health service: sweep, re-check after an edit, detail probe, usage records
- [x] 1.4 Routes `GET /providers/health`, `POST /providers/{uid}/check`; `connection_uid` on list-models
- [x] 1.5 Provider attention source (`provider_key_rejected`, `provider_unreachable`)
- [x] 1.6 Wiring, contracts, tests

## 2. Web UI

- [x] 2.1 Provider list marks every failing row from the kept verdicts
- [x] 2.2 The detail probe names its connection; the list refetches after it
- [x] 2.3 Overview runs a provider's Test again in place

## 3. Docs and canvas

- [x] 3.1 Model providers and Overview guides (en, zh)
- [x] 3.2 Agents canvas provider list and Shell canvas Overview boards
