## 1. Daemon

- [x] 1.1 Bound the spawn-lock wait and record the holder's pid in the lock file
- [x] 1.2 Exit 0 when the port is held by this vault's own daemon; log duplicate starts at WARNING
- [x] 1.3 Force a predecessor that outlives the self-restart wait
- [x] 1.4 Follow `COFFER_DAEMON_EXIT_WITH_PID` out

## 2. Clients

- [x] 2.1 CLI: stop killing a spawn it gave up on; wait 30 s
- [x] 2.2 Shim: wait for a running but busy daemon before spawning
- [x] 2.3 `coffer daemon restart` forces out a daemon that will not stop; `stop` waits the grace
- [x] 2.4 `coffer daemon status` lists other daemon processes of the vault
- [x] 2.5 Desktop restart forces out a daemon that does not answer or keeps its port

## 3. Harness, tests, docs

- [x] 3.1 e2e daemon script, Playwright configs and shim tests pass the exit-with pid
- [x] 3.2 Tests for every new scenario
- [x] 3.3 Architecture page (en, zh) and the daemon guide
