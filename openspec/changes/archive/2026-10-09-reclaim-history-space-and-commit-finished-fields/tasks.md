## 1. History database space

- [x] 1.1 Write the pre-migration copy with `VACUUM INTO`; remove a half-written copy on failure; keep pruning the companions of copies an earlier build took
- [x] 1.2 `reclaim_free_pages`: `VACUUM` and truncate the WAL when free pages are ≥ 50 % of the file and ≥ 8 MB
- [x] 1.3 The retention worker runs it after each pass; the composition root hands it the history file
- [x] 1.4 Tests: compact copy includes WAL content and has no free pages; failed copy leaves nothing; reclaim thresholds; worker order

## 2. Typed channel settings

- [x] 2.1 `useSettingDraft` commits on blur or Enter, not after a delay, and skips a value equal to the last saved one
- [x] 2.2 The quiet windows, idle period, title and app id fields commit through it
- [x] 2.3 Tests: a half-typed value is never sent; blur and Enter commit

## 3. Docs

- [x] 3.1 ADR audit-and-retention: reclaiming space, compared options
- [x] 3.2 ADR every-vault-write-is-a-validated-commit-naming-its-writer: coalescing consecutive saves considered and rejected
- [x] 3.3 docs-site persistence (en, zh): backups and space reclamation; channels guide (en, zh): typed settings commit on blur or Enter
