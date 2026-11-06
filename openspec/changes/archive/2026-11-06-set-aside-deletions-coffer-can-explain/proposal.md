## Why

From 2026-10-09 to 2026-11-05 the deletion breaker held the owner's vault 13
times (28–136 files each). The vault's history shows all of them were the memory
sync removing hub memories and Tidy runs the owner had started; none was a real
loss. Three times the same hold was also asked twice: confirmed, then a
plaintext stop, whose fix moved the vault and voided the confirmation. Options
are argued in the 2026-11-06 addendum to ADR `sync-deletion-breaker`.

## What Changes

- The breaker sets aside a loss whose newest deleting commit is the memory
  sync's or an agent's Tidy, unless the area would be emptied.
- A "delete" answer is remembered by file while the remote tip is unchanged.
- The `sync.round` / `sync.continue` log lines carry the round's detail, path,
  hold direction and counts.
- Docs: the guide no longer says both that secret ciphertext never conflicts and
  that it offers two choices (the second is a join's differing file).

## Impact

- `domain/sync/breaker.py`, `application/sync/round_guard.py`,
  `round_engine.py`, `round_answers.py`, `infrastructure/sync/local_state.py`,
  `application/sync/service.py`; spec vault-sync; vault-sync guide and
  architecture (en, zh).
