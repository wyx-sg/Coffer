## 1. Curation naming

- [x] 1.1 RENAMED deltas for the two vault-sync requirements
- [x] 1.2 Update every citation quoting the old titles

## 2. Retired ids

- [x] 2.1 Replace `T-0xx`, `TEST-0xx` and `P1-1` ids in comments, docstrings and e2e headers with the requirement title or drop them
- [x] 2.2 Add the task and review-finding id forms to the citation gate's retired-id rule, with tests

## 3. Citation gate

- [x] 3.1 Recognise `spec <cap>: "Title"`, `` spec `cap` "Title" `` and `spec **cap** "Title"`, with tests
- [x] 3.2 Stop reading a quote that closes a string literal as a title, with tests

## 4. Harness ADR

- [x] 4.1 Set "Industrial-Grade Harness, Built in Layers" to Accepted with a note on what shipped and what was not built; update the ADR index

## 5. Close

- [x] 5.1 Run make verify
- [x] 5.2 Archive the change

## Note

OpenSpec has no delta for renaming a scenario inside a requirement: a MODIFIED
block that drops an old scenario name is refused. After archiving, the three
scenario names that still said "tidy" were renamed in
`openspec/specs/vault-sync/spec.md` directly, together with their acceptance
markers, in the same PR.
