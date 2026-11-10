# Timeouts and Intervals Count Time the Computer Slept

**Status**: Accepted
**Date**: 2026-11-10
**Deciders**: Yuxing Wu
**Related**: [Sync Only Pulls and Pushes the Vault Repository](sync-applies-clean-merges-and-stops-on-any-conflict.md), spec vault-sync "Let a sleeping computer neither stall nor fail a round"

## Context

A MacBook with its lid closed sleeps, but PowerNap wakes it for about two
seconds every quarter hour. On 2026-11-08 the hourly sync round started in one
of those wakes, sent `git fetch`, and the machine slept again a second later.
The round's 120-second timeout was `subprocess.run(timeout=…)`, and the
worker's hour was `asyncio.wait_for`. Both count on `time.monotonic`, which on
macOS is `mach_absolute_time` and on Linux `CLOCK_MONOTONIC`: neither runs
while the machine sleeps. The 120 seconds were collected two seconds per wake,
so the fetch timed out four and a half hours later; the next hour of awake time
had not passed 35 hours after that, so the Sync page kept showing a stale
failure after the person opened the laptop. The timeout also escaped as a
generic `VaultGitError`, so the round read "failed" rather than "Remote
unreachable", although `remote.classify` already listed "timed out after" as a
network problem.

## Options Considered

### Option A — Count deadlines and waits on a clock that runs through sleep; abandon stalled transfers; retry once after sleep (chosen)

A small `sleep_clock` reads `CLOCK_BOOTTIME` (Linux) or `clock_gettime(CLOCK_MONOTONIC)`
(macOS, where that clock counts sleep), chosen by what the `time` module
offers. A remote git call asks `communicate` in five-second steps and checks
the deadline on that clock between them; the worker waits in 15-second steps
the same way. Git is given `http.lowSpeedLimit=1000` / `http.lowSpeedTime=30`
so a dead connection fails on its own. A call that failed after the machine
slept while it ran is tried once more, and a timeout comes back as a failed
process so it is classified `unreachable`.

Pros: a round due during sleep runs within 15 seconds of waking; a call cut by
sleep ends within seconds of waking; the person sees the true cause. Cons: a
poll loop instead of a single blocking call, and a round may still start in a
two-second dark wake and be cut (it is then retried, and the next full wake
catches up).

### Option B — Detect sleep and wake through the OS (IOKit power notifications, systemd-logind)

Run a round on the wake notification and skip dark wakes. Loses because it
needs a native binding per OS behind the platform port for a problem a clock
read solves, and still needs Option A's deadline for a call already in flight.

### Option C — Only lengthen the timeout or shorten the interval

Loses because neither changes what the clock counts: a longer timeout makes the
stall longer, and a shorter interval still waits in awake time.

### Option D — Hold a sleep assertion (`caffeinate`) for the length of a round

Keeps the machine awake until the round ends. Loses because Coffer would be
keeping a closed laptop awake on battery for a background chore, and a dark
wake can still end before the assertion is taken.

## How comparable tools handle it

- **Syncthing** pings each peer connection and closes one that stops
  answering, then redials, so a sleep shows up as a dead connection that is
  replaced after wake rather than waited on.
- **Native desktop sync clients** (Dropbox, OneDrive) resume when the OS
  reports a wake (Option B); they are native apps that already hold those
  hooks.
- **git** itself offers `http.lowSpeedLimit` / `http.lowSpeedTime` for exactly
  the stalled-connection case, and curl's timers run on a clock that counts
  sleep on macOS.

Coffer takes the clock-based route Syncthing takes and git's own stall guard,
without adding a native wake listener.

## Decision

Option A. Deadlines and waits a person reads as wall time count on
`application/runtime/sleep_clock.py`; remote git calls abandon stalled
transfers, retry once after sleep, and report a timeout as unreachable.

## Consequences

- A new background loop that waits "every N minutes" should wait on
  `sleep_clock` in steps, as the sync worker does; Coffer's other loops still
  count awake time and can move when one shows the same symptom.
- The stall guard applies to HTTP(S) remotes; an SSH remote relies on the
  sleep-counting deadline alone.
