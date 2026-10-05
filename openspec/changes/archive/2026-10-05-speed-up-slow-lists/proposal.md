## Why

The Conversations page took 1–4 seconds to open, every time. Asking Codex for its threads
costs about a second whatever the page size, and every later page and every 10-second
refresh asked every agent again. Other pages were slow for similar reasons: Codex hooks
re-listed every plugin once per plugin (4.6 s), Claude Code's native-memory scan re-read
transcripts to recover project paths (1.2 s), the memory partition list parsed every note
of every partition, the sync machine list ran `git log` on every read, and the attention
report asked its sources one after another.

## What Changes

- The cross-agent session listing keeps each agent's last answer in memory for a few
  minutes, serves it at once and refreshes it in the background; concurrent reads share one
  request, and pages after the first reuse the answers the first one kept.
- The Conversations list and an agent's Sessions tab refresh every 30 seconds instead of 10,
  and the Conversations entry in the sidebar fetches the first page when pointed at.
- Codex hooks list each plugin once; the native-memory scan, the memory partition summaries
  and the sync machine list reuse work whose inputs have not changed; the attention report
  asks its sources concurrently, and the tray reads it every 30 seconds.
- Long lists that are fetched whole render the first screen and the rest as the reader
  scrolls.

## Impact

- Backend: agent sessions listing, hooks, native memory scan, memory partitions, sync
  machines, attention. Frontend: polling intervals, Conversations prefetch, progressive rows.
- Specs: agent-registry.
