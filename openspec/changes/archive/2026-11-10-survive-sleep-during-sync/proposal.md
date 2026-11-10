## Why

A laptop that sleeps with the lid closed still wakes for two seconds every
quarter hour (PowerNap). A sync round that started in one of those wakes sent
`git fetch`, the machine slept a second later, and the connection died. The
120-second timeout counted only awake time (`time.monotonic` stops while the
machine sleeps), so it took four and a half hours of sleep to expire, and the
round was recorded as a plain failure. The hourly interval counted the same
way, so no new round ran for 35 hours and the Sync page kept saying the last
round failed after the person had opened the laptop again.

## What Changes

- A remote git call (fetch, push, ls-remote) counts its 120-second deadline on
  a clock that keeps running while the computer sleeps.
- A remote git call abandons a transfer slower than 1000 bytes a second for 30
  seconds, so a connection a sleep cut fails soon after waking.
- A remote git call that fails after the computer slept while it ran is tried
  once more.
- A timed-out remote call is reported as **Remote unreachable**, like any other
  network failure, instead of a generic failed round.
- The sync worker's wait between rounds counts time asleep, so a round that
  fell due during sleep runs within 15 seconds of waking.

## Impact

- `backend/coffer/application/runtime/sleep_clock.py` (new),
  `backend/coffer/infrastructure/vault/git.py`, `remote.py`,
  `backend/coffer/application/sync/worker.py`.
- Spec `vault-sync`: one added requirement.
- ADR `timeouts-and-intervals-count-time-the-computer-slept`.
- Docs: `docs-site/guides/vault-sync.md`, `docs-site/architecture/vault-sync.md`
  and their `zh/` pages.
