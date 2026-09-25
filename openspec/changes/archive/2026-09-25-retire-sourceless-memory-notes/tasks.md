## 1. Retire sourceless notes

- [x] 1.1 `RetiredNote.sources_gone`, written to and read from `RETIRED.md` only when set
- [x] 1.2 `retire_sourceless` in `distil.py`, run before routing on the model and mechanical paths; counted in `DistilResult.retired`
- [x] 1.3 Routing's retired-subjects list skips `sources_gone` records
- [x] 1.4 Tests: unit (sweep, record round-trip, routing exclusion) and integration (the `global` → project move end to end), with acceptance markers

## 2. Docs

- [x] 2.1 `data-model.md`, the `DistilResultOut.retired` description
- [x] 2.2 docs-site memory guide / architecture page
