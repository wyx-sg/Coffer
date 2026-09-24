# The Daemon Binds a Fixed Port and Refuses to Start Without It

**Status**: Accepted
**Date**: 2026-09-13
**Deciders**: Yuxing Wu
**Related**: [Detect-or-Spawn](daemon-detect-or-spawn.md), [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md), [Desktop Shell Over a Shared Frontend](desktop-shell-over-a-shared-frontend.md), spec daemon "Bind a fixed, settable port", spec daemon "Manage the daemon from the command line", PR #364, PR #376, PR #412

## Context

The daemon serves the web UI from its own loopback origin (spec daemon "Serve
the built web UI from the daemon's own origin"), so its port is part of a URL a
person uses: a bookmark, a typed address, a restored tab. The port is also the
browser's storage key: `localStorage` is keyed by origin, so the UI language,
sidebar state, page size and preferred editor all belong to
`http://127.0.0.1:<port>`.

The daemon used to take the first free port in 8000–8009. When 8000 was busy —
a stray dev server, a daemon from a test run under a throwaway `HOME`, or an
orphaned Coffer daemon — it silently moved to 8001, the bookmark stopped
working, and the browser's stored preferences reset. Nothing connected the two
events for the user. Ten orphaned daemons were once found holding all of
8000–8009, at which point no daemon could start at all.

Two further constraints decide *where* a port setting can live:

- the port is chosen in `bootstrap.acquire`, before the database is opened and
  before migrations run, so no database-backed setting can carry it;
- the daemon is spawned detached by whichever client first needs one
  ([Detect-or-Spawn](daemon-detect-or-spawn.md)) and inherits that client's
  environment — a shell profile reaches the user's own terminal and nothing
  else, least of all a GUI-launched agent's MCP shim.

## Options Considered

### Option A — Fixed default 8000, overridable in a pre-database config file, refuse rather than fall back (chosen)

With nothing configured the daemon binds exactly `127.0.0.1:8000`
(`DEFAULT_PORT` in `infrastructure/daemon/config.py`). A user who needs another
port sets it with `coffer daemon port set <n>`, which writes it into
`~/.coffer/daemon-config.json` — mode `0600`, merged rather than replaced, read
with nothing but the standard library before the bind. If the port cannot be
bound the daemon refuses to start and prints one message naming the process
that holds it and each way out (`port_alloc.fixed_port_conflict_message`):
stop that process, `coffer daemon port set <other>`, or — only when the failing
port is not the default — `coffer daemon port clear`.

Pros: the origin never moves, so bookmarks and browser-stored preferences
survive restarts; a conflict is visible and named instead of silent; the setting
is reachable when the daemon is down, which is exactly when it is needed. Cons:
a machine whose 8000 is permanently taken cannot start Coffer until the user
runs one command. This is the conventional choice for local services with a web
UI — Ollama, Syncthing, Grafana, Home Assistant and Tailscale all fix a default
and let it be changed — and it wins because a predictable origin is worth more
than an automatic one.

### Option B — Scan a range and take the first free port

The design this replaced. Pros: always starts. Cons: the origin drifts, which
breaks bookmarks and resets origin-keyed browser state without explanation; a
scan cannot prefer the port the bookmark names; drifted daemons accumulate
(8000–8009 filled once). Tools that scan forward — Jupyter, Vite — are
development tools that print their URL on every start and that nobody
bookmarks. Loses. The scan survives only as the `COFFER_PORT_RANGE_START` /
`COFFER_PORT_RANGE_END` override (`bootstrap._bind_port`,
`port_alloc.bind_free_socket`), which the test suite sets so concurrent test
daemons stay away from the real 8000; no user-facing surface sets it.

### Option C — Scan by default, with an optional user-pinned port

The intermediate design shipped in PR #364: pin a port in `daemon-config.json`
and it is bound exactly; pin nothing and the scan runs. Pros: never fails to
start out of the box. Cons: the default experience — the one most users get —
still drifts. Keeping the scan and relying on the desktop shell to find the
port would work for the shell, which reads the port from a file, and keep
punishing the browser host, which the shell does not replace. Inverted by PR
#376.

### Option D — An environment variable (`COFFER_PORT`)

Pros: conventional, no file. Cons: the daemon is spawned by whichever client
comes first and inherits that client's environment. An agent launched from the
Dock has never read the user's shell profile, so its shim would spawn a daemon
on the default port while a terminal-spawned one used the variable — the drift
again, by a different route. Loses.

### Option E — A row in the settings table

Pros: one place for all settings, audited, reachable over REST. Cons: the port
must be known before the database is opened and before migrations have created
any table; a setting the daemon needs in order to start cannot live in the
daemon's own database. The vault database also syncs between machines
([Vault Sync](vault-sync.md)), and a port is a fact about one machine. Loses.

### Option F — An OS-assigned port (`bind(0)`) published only through the discovery file

Pros: never conflicts. Cons: every restart gets a new origin — the worst case
of Option B made the norm. Clients that read `daemon.json` would cope; the
browser, which is the reason the port matters, would not. Loses.

### Option G — A Unix domain socket instead of a TCP port

Pros: no port to conflict, file permissions as access control. Cons: a browser
cannot load a page from a Unix socket, and the web UI is served by the daemon.
It would need a TCP listener beside it for the UI, which puts the port question
back. Loses.

## Decision

The daemon binds exactly one loopback port: the one in
`~/.coffer/daemon-config.json` if the user set one, otherwise 8000. It never
falls back. If the port is taken it refuses to start and names the holder and
the fixes; a Coffer daemon found holding it is identified as such and is not
killed automatically, since it is most often the user's own daemon still
warming up and otherwise belongs to another vault.

`daemon-config.json` is the one piece of configuration that is not in SQLite.
It holds the settings a daemon needs before it opens its database or that must
not sync: the port, the machine's display name, the cached derived machine id,
and the per-machine experimental-feature switches. Writes merge, keep keys this
build does not know (so a file written by a newer build survives an older one),
and drop retired keys. The file carries no `version` key; earlier builds wrote
one that nothing read, and it is kept as an unknown key where it still exists.
An unreadable file warns and falls back to the default rather than stopping the
boot, since a daemon that cannot boot cannot be repaired from the UI it serves.

The setting is changed from the CLI only (`coffer daemon port show|set|clear`),
which works with no daemon running. It has no REST route or settings panel: a
port that is correct by default does not earn one, and the escape hatch belongs
where a squatted port is diagnosed. A change takes effect at the next start;
`coffer daemon restart` applies it.

## Consequences

- A bookmark to the UI works across restarts, and so do the preferences the
  browser stored against that origin. The desktop shell gains nothing from it
  directly (its page origin is `tauri://localhost`), but the browser host the
  shell does not replace does.
- A port conflict is a startup failure, not a silent move. The daemon does not
  start until the user acts. [Detect-or-Spawn](daemon-detect-or-spawn.md)'s
  client-side pre-check prints the same message before spawning.
- Restart has to rebind the same port immediately, so the fixed-port bind sets
  `SO_REUSEADDR` (a port whose accepted connections are in `TIME_WAIT` would
  otherwise refuse) and makes four attempts 0.3 s apart for the moment the
  outgoing daemon has not let go (`port_alloc.bind_fixed_socket`).
- The scan path must **not** set `SO_REUSEADDR`. On Linux the option also lets
  two sockets bind the same port while neither is listening, and a daemon is
  bound-but-not-listening for its whole boot window; setting it there let a
  second daemon bind the first one's port. macOS refuses that bind, so only the
  Linux CI run found it (`test_port_alloc.py` pins it).
- The port change is not audited. It is process configuration written with no
  daemon running, so the audit table is unreachable on exactly the path that
  matters; recording it only when a daemon happens to be up would be less
  honest than recording none.
- The shim still has to cope with a restarted daemon: the port is stable but the
  token changes on every start ([stdio Shim Bridge](stdio-shim-bridge.md)).
