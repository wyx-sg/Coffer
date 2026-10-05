## 1. Backend

- [x] 1.1 `secret-notes` vault state document (label, description), port and store
- [x] 1.2 `PUT /api/v1/secrets/notes`; list carries `label` and `description`; delete and release drop notes; audit `secret_notes_updated`
- [x] 1.25 `POST /api/v1/secrets` accepts `{label, value}` and mints `secret/<uuid4 hex>`
- [x] 1.4 One-time migration of existing refs to fixed ids
- [x] 1.5 Audit every use of a secret; `GET /api/v1/secrets/uses`
- [x] 1.6 Citation index in `derived/`, kept current by resource and skill writes
- [x] 1.7 `created_for` claimed at registration; release only what was minted for the deleted resource
- [x] 1.3 Tests with acceptance markers; contract regenerated

## 2. Frontend

- [x] 2.0 Add secret dialog: label + value, then show `coffer://secret/<id>` with Copy
- [x] 2.1 Detail sheet with label and description in place; readable default names; Used by plain text; search over label and description; i18n en + zh; tests

## 3. Docs

- [x] 3.1 guides/secrets (en + zh)
