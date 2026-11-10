## ADDED Requirements

### Requirement: Let a sleeping computer neither stall nor fail a round
A remote git call (fetch, push, `ls-remote`) MUST count its 120-second deadline
on a clock that keeps running while the computer sleeps, MUST abandon a
transfer slower than 1000 bytes a second for 30 seconds, and MUST be tried once
more when it fails after the computer slept while it ran. A timed-out call is
the remote being unreachable, not a generic failure. The worker's wait between
rounds MUST count time asleep too, so a round that fell due while the computer
slept runs within 15 seconds of waking rather than after another interval of
awake time.

#### Scenario: a remote call cut short by sleep is retried and its deadline counts the sleep
- **GIVEN** a fetch whose process hangs while the computer sleeps past its 120-second deadline
- **WHEN** the computer wakes
- **THEN** the process is stopped and reported as timed out because the computer slept, the call is tried once more, and a timeout is classified as unreachable

#### Scenario: a round that fell due during sleep runs soon after waking
- **GIVEN** the worker waiting an hour for the next round
- **WHEN** the computer sleeps for longer than that hour and wakes
- **THEN** the wait ends within the worker's poll step instead of an hour of awake time later
