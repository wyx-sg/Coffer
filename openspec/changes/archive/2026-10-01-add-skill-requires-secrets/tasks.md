## 1. Backend

- [x] 1.1 Parse `requires.secrets` in the mapping form, refuse unknown mapping keys with a warning
- [x] 1.2 Carry `requires_secrets` (name, `is_set`) on the skill read model from the secret store's presence check
- [x] 1.3 Raise a `skill_missing_secret` attention item per skill whose declared secret is not set
- [x] 1.4 Regenerate the skill-manager contract and the frontend types

## 2. Web UI

- [x] 2.1 List declared secrets on the Requires tab, a missing one opening Secrets
- [x] 2.2 Show a missing secret on the library row and as a banner; the Overview action opens Secrets

## 3. Docs and tests

- [x] 3.1 Describe `requires.secrets` in the skills and skill-library guides (en and zh)
- [x] 3.2 Backend unit and integration tests, frontend tests, with acceptance markers
