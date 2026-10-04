## 1. Backend

- [x] 1.1 Refuse the `ollama` protocol on create and on an edit that moves a connection onto it (`PROVIDER_PROTOCOL_RETIRED`, 422)
- [x] 1.2 Keep a stored `ollama` connection readable, listed, edited and deleted; refuse switching an agent onto it
- [x] 1.3 Replace `PROVIDER_INTERNAL_ONLY`; drop the introspector's `ollama` default URL and the key-less `ollama` create path
- [x] 1.4 Update the unit and integration tests and their acceptance markers

## 2. Frontend

- [x] 2.1 Stop offering `ollama` in the Add dialog (plan, presets, schemas, edit protocols) and remove its copy
- [x] 2.2 Keep a stored `ollama` connection rendering on the list and detail pages

## 3. Spec and docs

- [x] 3.1 provider-switching delta and `data-model.md`
- [x] 3.2 Docs site (en and zh): providers guide, glossary, FAQ, error codes, architecture pages
- [x] 3.3 Regenerate contracts and the backend-keys fixture
