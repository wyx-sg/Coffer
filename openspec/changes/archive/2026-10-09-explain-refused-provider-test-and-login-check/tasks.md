## 1. Backend

- [x] 1.1 `StoredKeyDestinationRefused` (reason `stored_key_destination`) raised by the introspection gate
- [x] 1.2 `LoginCheckCommandInvalid` with reason, field and command in the envelope details
- [x] 1.3 Tests: introspection routes assert the reason; CLI routes refuse a path-first login check and accept the file name

## 2. Frontend

- [x] 2.1 `useEndpointTest` returns `refused` for the destination refusal; `ProbeResult` renders it without the failure note
- [x] 2.2 Add CLI shows a login-check refusal at its field and clears it on edit; hint names the rule
- [x] 2.3 `labelNewKey` invalidates the secrets cache after the label write
- [x] 2.4 Tests: refusal vs failure verdict, field-level login-check refusal, cache settled after labelling

## 3. Docs

- [x] 3.1 Specs edited in place; docs-site providers and CLIs guides and error-code reference (en, zh)
